import streamlit as st
import boto3
import requests
import io
import os
import re
import re
from dotenv import load_dotenv
import base64
from moviepy.editor import *
from PIL import Image

load_dotenv()

# S3 bucket settings
s3client = boto3.client('s3', 
                        region_name = 'us-east-1',
                        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY'),
                        aws_secret_access_key = os.environ.get('AWS_SECRET_KEY')
                        )


# polly settings
pollyclient = boto3.client('polly',
                        region_name = 'us-east-1',
                        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY'),
                        aws_secret_access_key = os.environ.get('AWS_SECRET_KEY')
                        )

bucket_name = os.environ.get('USER_BUCKET_NAME')

def display_video_from_images():
    video_stream = s3client.get_object(Bucket=bucket_name, Key='video_output/' + 'video_from_images.mp4')['Body'].read()

    # Stream the video using st.video()
    st.video(video_stream, start_time=0)

    # Delete the original file
    response_audio = s3client.list_objects_v2(Bucket=bucket_name, Prefix='image_input/audio/')
    for obj in response_audio['Contents'][1:]:
        s3client.delete_objects(Bucket=bucket_name, Delete={'Objects': [{'Key': obj['Key']}]})

    response_image = s3client.list_objects_v2(Bucket=bucket_name, Prefix='image_input/')
    for obj in response_image['Contents'][1:]:
        if (('.png' or '.jpg') in obj['Key']):
            s3client.delete_objects(Bucket=bucket_name, Delete={'Objects': [{'Key': obj['Key']}]})

def processed_audio_from_texts():
    # Specify the folder in the input bucket containing the text files
    input_folder_path = 'image_input/text/'
    # Get the list of objects (text files) in the input folder
    objects = s3client.list_objects(Bucket=bucket_name, Prefix=input_folder_path)
    
    # Set the Polly voice and parameters
    voice_id = 'Joanna'
    output_format = 'mp3'
    engine = 'standard'
    # Iterate through the objects and generate audio for each text file
    for obj in objects['Contents']:
        # Get the text from the object (text file)
        text = s3client.get_object(Bucket=bucket_name, Key=obj['Key'])['Body'].read().decode('utf-8')
        #extracting the file path
        file_path = obj['Key']
        # Regex pattern to get the text after the last slash
        pattern = r"/([^/]+)$"
        # Search for the pattern in the file_path
        match = re.search(pattern, file_path)
        if match:
            # Extract the text after the last slash from the match object
            text_file_name = match.group(1)
            # Remove ".txt" extension from file names
            file_names_without_ext = os.path.splitext(text_file_name)[0]
            # Set the audio file names
            audio_file_name = 'image_input/audio/'+ file_names_without_ext + '.mp3'
            # Generate the speech with Polly
            response = pollyclient.synthesize_speech(
                Text=text,
                VoiceId=voice_id,
                OutputFormat=output_format,
                Engine=engine
            )
            # Save the audio file to S3
            s3client.put_object(Body=response['AudioStream'].read(), Bucket=bucket_name, Key=audio_file_name)
            s3client.delete_object(Bucket=bucket_name, Key=file_path)

def processed_video_from_images():
    with st.spinner('Processing the images...'):
        image_files=[]
        audio_files=[]
        final_clip = None

        # List of image and audio files
        response_audio = s3client.list_objects_v2(Bucket=bucket_name, Prefix='image_input/audio/')

        for obj in response_audio['Contents'][1:]:
            filename_audio=obj['Key'].replace('image_input/audio/', '')
            s3client.download_file(bucket_name, 'image_input/audio/'+f'{filename_audio}', f'{filename_audio}')
            audio_files.append(filename_audio)

        response_image = s3client.list_objects_v2(Bucket=bucket_name, Prefix='image_input/')

        for obj in response_image['Contents'][1:]:
            filename_image=obj['Key'].replace('image_input/', '')
            if (('.png' or '.jpg') in filename_image):
                s3client.download_file(bucket_name, 'image_input/'+f'{filename_image}', f'{filename_image}')
                # Open an image
                image = Image.open(filename_image)
                # Resize the image
                resized_image = image.resize((640, 360))
                # Save the resized image
                resized_image.save(filename_image)
                image_files.append(filename_image)

        for i in range(len(image_files)):
            if final_clip is None:
                final_clip = ImageClip(image_files[i], duration=5).set_audio(AudioFileClip(audio_files[i]))
            else:
                # Add the audio to the portion of the video after the insertion point
                final_clip = concatenate_videoclips([final_clip, ImageClip(image_files[i], duration=5).set_audio(AudioFileClip(audio_files[i]))])
        
        if (final_clip!=None):
            final_clip.write_videofile('video_from_images.mp4', fps=24)

            # Upload the final video to S3
            s3client.upload_file('video_from_images.mp4', bucket_name, 'video_output/'+'video_from_images.mp4')

            # Delete local files
            os.remove('video_from_images.mp4')
            for j in range(len(image_files)):
                os.remove(image_files[j])
                os.remove(audio_files[j])
        
            display_video_from_images()

def get_images():
    count=0

    # Loop through all uploaded images
    for image in images:
        count+=1
        with st.spinner('Uploading images to S3 bucket...'):
            # Upload image to S3
            s3client.upload_fileobj(image, bucket_name, 'image_input/'+image.name)
        
    if (count==len(images) and count!=0):
        st.success("Images uploaded successfully!")
        # processed_video_from_images()

        #Trigger DAG with file and language as parameters
        airflow_url = os.environ.get('AIRFLOW_URL_IMAGE')
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Authorization": os.environ.get('AIRFLOW_AUTH'),
        }
        json_data = {"conf" : {"test": 'test'}}
        response = requests.post(airflow_url, headers=headers, json=json_data)
        if response.status_code == 200:
            response_json = response.json()
            st.write(
                "DAG triggered successfully",
                response_json["execution_date"],
                response_json["dag_run_id"],
            )

            response_my_video = s3client.list_objects(Bucket=bucket_name, Prefix='video_output/')

            for obj in response_my_video['Contents'][1:]:
                if ('video_from_images.mp4' in obj['Key']):
                    display_video_from_images()

        else:
            st.write(f"Error triggering DAG: {response.text}", None, None)

if __name__=="__main__":
    st.markdown(
         f"""
         <style>
         .stApp {{
             background-image: url("https://user-images.githubusercontent.com/108916132/230649126-a68a45d3-c1b2-4868-822b-435e0ccbf396.jpg");
             background-attachment: fixed;
             background-size: cover
         }}
         </style>
         """,
         unsafe_allow_html=True
     )

    # Title of the app
    st.title("Upload Images to S3")

    # Add some headers and subtitles to the app
    st.write('#### Step 1: Upload images to analyse')
    st.write('#### Step 2: Wait for Processing and Streaming')

    # Allow user to upload multiple images
    images = st.file_uploader("Upload your images", accept_multiple_files=True)

    get_images()