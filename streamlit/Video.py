import streamlit as st
import boto3
import re
from pytube import YouTube
import requests
import io
import os
from dotenv import load_dotenv
import base64
from moviepy.editor import *
import math
from PIL import Image
from datetime import timedelta

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

user_bucket = os.environ.get('USER_BUCKET_NAME')

# Define a logo image and display it in the title section
st.set_page_config(page_title='Vaider', page_icon="🎥")

st.markdown(
         f"""
         <style>
         .stApp {{
             background-image: url("https://user-images.githubusercontent.com/108916132/230253159-aa1fbd18-1f2e-4071-bdd7-0c6ab9758638.png");
             background-attachment: fixed;
             background-size: cover
         }}
         </style>
         """,
         unsafe_allow_html=True
     )

# Streamlit app
st.title('Visual aid for any video')

# Add some headers and subtitles to the app
st.write('#### Step 1: Enter YouTube Video URL')
st.write('#### Step 2: Wait for Processing and Streaming')

# Get YouTube video URL from user input
video_url = st.text_input('Enter YouTube Video URL')

def display_video(video_title):
    video_stream = s3client.get_object(Bucket=user_bucket, Key='video_output/' + f'{video_title}.mp4')['Body'].read()

    # Stream the video using st.video()
    st.video(video_stream, start_time=0)

def processed_video(videofile):
    with st.spinner('Processing video...'):
        final_clip = None
        # Download video file from S3 to local directory
        s3_video_file_name = videofile
        local_video_file_name = videofile
        s3client.download_file(user_bucket, 'video_input/'+s3_video_file_name + '.mp4', local_video_file_name)

        # Download audio file from S3 to local directory
        response = s3client.list_objects(Bucket=os.environ.get('USER_BUCKET_NAME'), Prefix='video_input/audio/')

        # Get all the wav files and sort them by name
        audio_files = sorted([obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.wav' or '.mp3')])
        
        for i, audio_file in enumerate(audio_files):
            s3client.download_file(user_bucket, 'video_input/audio/'+str(i)+'.wav', str(i)+'.wav')

        # Load the video
        my_video = VideoFileClip(local_video_file_name)
        video_duration = my_video.duration
        my_video_2 = my_video.subclip(0, math.floor(video_duration))

        processed_duration=0

        for i in range(0, math.ceil(my_video_2.duration/5)):

            # Load the audio
            my_audio = AudioFileClip(str(i)+'.wav')

            if (my_video_2.duration - processed_duration > 5):
                # Get the portion of the video before the audio insertion point
                before_audio = my_video_2.subclip(i*5, (i*5)+5)
            else:
                before_audio = my_video_2.subclip(i*5, (i*5) + my_video_2.duration - processed_duration)

            if final_clip is None:
                final_clip = concatenate_videoclips([before_audio.set_audio(my_audio), before_audio])
            else:
                # Add the audio to the portion of the video after the insertion point
                final_clip = concatenate_videoclips([final_clip, before_audio.set_audio(my_audio), before_audio])

            processed_duration+=5

        # final_clip_2 = concatenate_videoclips(final_clip, after_audio)
        # Export the final clip to a local file
        local_final_video_file_name = 'final_video_local.mp4'
        final_clip.write_videofile(local_final_video_file_name)

        # Upload the final video to S3
        s3_final_video_file_name = f'video_output/{videofile}'+'.mp4'
        s3client.upload_file(local_final_video_file_name, user_bucket, s3_final_video_file_name)

        # Delete local files
        os.remove(local_video_file_name)
        os.remove(local_final_video_file_name)
        for j in range(0, math.ceil(my_video_2.duration/5)):
            os.remove(str(j)+'.wav')

        ##############Delete S3 'video_name' folder####################
        # s3client.delete_objects(Bucket=user_bucket, Delete={'Objects': [{'Key': 'video_name/'}]})

    display_video(videofile)

def extract_frames(video_file):
    with st.spinner('Extracting frames from video...'):
        s3client.download_file(user_bucket, 'video_input/'+video_file + '.mp4', video_file)
        clip = VideoFileClip(video_file)

        video_duration = clip.duration
        for i in range (0, int(video_duration), 5):
            clip.save_frame(str(int(i/5))+'.png', i)
            s3client.upload_file(str(int(i/5))+'.png', user_bucket, 'video_input/frames/' + str(int(i/5)) + '.png')
            os.remove(str(int(i/5))+'.png')
        
        os.remove(video_file)

def processed_audio_from_texts():

    # Specify the folder in the input bucket containing the text files
    input_folder_path = 'image_input/text/'
    # Get the list of objects (text files) in the input folder
    objects = s3client.list_objects(Bucket=user_bucket, Prefix=input_folder_path)
    

    # Set the Polly voice and parameters
    voice_id = 'Joanna'
    output_format = 'mp3'
    engine = 'standard'

    # Iterate through the objects and generate audio for each text file
    for obj in objects['Contents']:
        # Get the text from the object (text file)
        text = s3client.get_object(Bucket=user_bucket, Key=obj['Key'])['Body'].read().decode('utf-8')
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
            s3client.put_object(Body=response['AudioStream'].read(), Bucket=user_bucket, Key=audio_file_name)
            s3client.delete_object(Bucket=user_bucket, Key=file_path)

def get_video():
    if video_url:
        try:
        # Get video stream URL using pytube
            yt = YouTube(video_url)
            video_title = yt.title
            st.write("Streaming " + f'"{video_title}"' + " to S3 bucket")
            stream_url = yt.streams.filter(progressive=True, file_extension='mp4', only_video=False).first().url

            # Upload video stream to S3 bucket
            s3_file_name = 'video_input/' + f'{video_title}.mp4'
            response = requests.get(stream_url, stream=True)
            with st.spinner('Uploading video...'):
                # Create a byte stream to hold the video data
                video_stream = io.BytesIO()
                for chunk in response.iter_content(chunk_size=480*480):
                    # Write each chunk to the byte stream
                    video_stream.write(chunk)
                # Reset the byte stream position to the beginning
                video_stream.seek(0)
                # Upload the byte stream to S3
                s3client.put_object(Bucket=user_bucket, Key=s3_file_name, Body=video_stream.read())

            st.write("Successfully uploaded " + f'"{video_title}"' + " to S3 bucket " + user_bucket)

        except Exception as e:
            st.write(f'Error: {e}')

        extract_frames(video_title)
        # processed_video(video_title)

if __name__=="__main__":
    get_video()
    processed_audio_from_texts()