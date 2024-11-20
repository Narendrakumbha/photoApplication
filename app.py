from flask import Flask, render_template, request, redirect, url_for
from google.cloud import storage
from flask_cors import CORS
import os
import requests

import vertexai
from vertexai.preview.generative_models import GenerativeModel, Image

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "composed-slice-437714-a8-8a1fc021fd53api.json"

# Initialize Google Cloud Storage client
BUCKET_NAME = "pythonimageappbucket"
CREDENTIALS_FILE = "composed-slice-437714-a8-54016734dfa9.json"
UPLOAD_FOLDER = 'static'

app = Flask(__name__)
CORS(app)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

storage_client = storage.Client.from_service_account_json(CREDENTIALS_FILE)

PROJECT_ID = "composed-slice-437714-a8"
REGION = "us-central1"
vertexai.init(project=PROJECT_ID, location=REGION)
generative_multimodal_model = GenerativeModel("gemini-1.5-pro-002")


# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route('/')
def index():
    """Homepage that allows uploading and listing images."""
    blobs = storage_client.list_blobs(BUCKET_NAME)

    # Fetch images and their corresponding captions
    images_with_captions = []

    for blob in blobs:
        if blob.name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            image_url = blob.public_url
            
            # Create the caption URL by changing the image extension to .txt
            caption_url = image_url.rsplit('.', 1)[0] + '.txt'
            
            # Fetch the caption from the caption URL
            try:
                response = requests.get(caption_url)
                response.raise_for_status()  # Raise an error for bad responses
                caption = response.text.strip()  # Get the caption text
            except requests.exceptions.RequestException:
                caption = "Could not fetch caption."

            # Append the image URL and its caption to the list
            images_with_captions.append((image_url, caption))

    # Render images with captions
    return render_template('index.html', images=images_with_captions)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    if 'file' not in request.files:
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file:
        if not file.filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            redirect(url_for('index'))
        
        if os.path.exists(os.path.join('./static', file.filename)):
            file.filename = file.filename.split('.')[0] + '_1.' + file.filename.split('.')[1]

        # Save file locally
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        # Upload file to Google Cloud Storage
        public_url = upload_to_gcs(file_path, file.filename)
        
        # generate caption and description
        if public_url:
            
            image = Image.load_from_file(file_path)
            response = generative_multimodal_model.generate_content(["Generate caption and description for this image? Given reponse without any heading for caption and description. Caption and Description should be seperated by double pipe(||) symbol.", image])
            caption = response.text.split('||')[0].strip()
            description = response.text.split('||')[1].strip()

            # create txt file with caption and description
            text_file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename.split('.')[0] + '.txt')
            with open(text_file_path, 'w') as f:
                f.write(f"{caption}\n{description}")
            
            upload_to_gcs(text_file_path, file.filename.split('.')[0] + '.txt')
        
        # Remove the local file
        print("Removing", file_path, text_file_path)
        os.remove(file_path)
        os.remove(text_file_path)

        return redirect(url_for('index'))

def upload_to_gcs(file_path, filename):
    """Upload a file to Google Cloud Storage."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_filename(file_path, if_generation_match=None)
    blob.make_public()  # Make the file publicly accessible
    print("uploaded ", blob.public_url)
    return blob.public_url

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)
