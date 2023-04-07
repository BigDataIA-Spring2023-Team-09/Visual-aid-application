import streamlit as st
import boto3
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

user_bucket = os.environ.get('USER_BUCKET_NAME')

def display_video(video_title):
    video_stream = s3client.get_object(Bucket=user_bucket, Key='video_output/' + f'{video_title}.mp4')['Body'].read()

    # Stream the video using st.video()
    st.video(video_stream, start_time=0)

    # Delete the original file
    response_audio = s3client.list_objects_v2(Bucket=user_bucket, Prefix='video_input/audio/')
    for obj in response_audio['Contents'][1:]:
        s3client.delete_objects(Bucket=user_bucket, Delete={'Objects': [{'Key': obj['Key']}]})

    response_image = s3client.list_objects_v2(Bucket=user_bucket, Prefix='video_input/frames/')
    for obj in response_image['Contents'][1:]:
        if (('.png' or '.jpg') in obj['Key']):
            s3client.delete_objects(Bucket=user_bucket, Delete={'Objects': [{'Key': obj['Key']}]})

def processed_video(videofile, frequency):
    if frequency=='5sec':
        f=5
    else:
        f=10
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

        for i in range(0, math.ceil(my_video_2.duration/f)):

            # Load the audio
            my_audio = AudioFileClip(str(i)+'.wav')

            if (my_video_2.duration - processed_duration > f):
                # Get the portion of the video before the audio insertion point
                before_audio = my_video_2.subclip(i*f, (i*f)+f)
            else:
                before_audio = my_video_2.subclip(i*f, (i*f) + my_video_2.duration - processed_duration)

            if final_clip is None:
                final_clip = concatenate_videoclips([before_audio.set_audio(my_audio), before_audio])
            else:
                # Add the audio to the portion of the video after the insertion point
                final_clip = concatenate_videoclips([final_clip, before_audio.set_audio(my_audio), before_audio])

            processed_duration+=f

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

    display_video(videofile)

def extract_frames(video_file, frequency):
    with st.spinner('Extracting frames from video...'):
        video_file=video_file.replace('.mp4', '')
        s3client.download_file(user_bucket, 'video_input/'+video_file + '.mp4', video_file)
        clip = VideoFileClip(video_file)

        video_duration = clip.duration
        for i in range (0, int(video_duration), 5):
            clip.save_frame(str(int(i/5))+'.png', i)
            s3client.upload_file(str(int(i/5))+'.png', user_bucket, 'video_input/frames/' + str(int(i/5)) + '.png')
            os.remove(str(int(i/5))+'.png')
        
        os.remove(video_file)

def get_video_youtube():
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
                for chunk in response.iter_content(chunk_size=640*360):
                    # Write each chunk to the byte stream
                    video_stream.write(chunk)
                # Reset the byte stream position to the beginning
                video_stream.seek(0)
                # Upload the byte stream to S3
                s3client.put_object(Bucket=user_bucket, Key=s3_file_name, Body=video_stream.read())

            st.write("Successfully uploaded " + f'"{video_title}"' + " to S3 bucket " + user_bucket)

        except Exception as e:
            st.write(f'Error: {e}')

        # extract_frames(video_title, frequency)

        #Trigger DAG with file and language as parameters
        airflow_url = os.environ.get('AIRFLOW_URL')
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Authorization": os.environ.get('AIRFLOW_AUTH'),
        }
        json_data = {"conf" : {"video_title": video_title, "frequency": frequency}}
        response = requests.post(airflow_url, headers=headers, json=json_data)
        if response.status_code == 200:
            response_json = response.json()
            st.write(
                "DAG triggered successfully",
                response_json["execution_date"],
                response_json["dag_run_id"],
            )
        else:
            st.write(f"Error triggering DAG: {response.text}", None, None)

        # processed_video(video_title)

if __name__=="__main__":
    # Define a logo image and display it in the title section
    st.set_page_config(page_title='Vaider', page_icon="🎥")

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

    # Streamlit app
    st.title('Visual aid for any video')

    # Add some headers and subtitles to the app
    st.write('#### Step 1: Upload Video')
    st.write('#### Step 2: Wait for Processing and Streaming')

    # Get video input method from user
    input_method = st.radio('Select video input method:', ('Upload video from YouTube', 'Upload video from local directory'))

    # Show appropriate widget based on user input method
    if input_method == 'Upload video from local directory':
        video_file = st.file_uploader('Upload Video File', type='mp4')
    else:
        # Get YouTube video URL from user input
        video_url = st.text_input('Enter YouTube Video URL')

    # Add a dropdown for frame frequency selection
    frequency = st.selectbox('Please select frame frequency:', ('5sec', '10sec'))

    # Process the video and show the result
    if st.button('Process Video'):
        if input_method == 'Upload video from local directory':
            # Process the uploaded video file
            if video_file is not None:
                s3client.upload_fileobj(video_file, user_bucket, 'video_input/'+video_file.name)
                st.write(f"File uploaded to S3 bucket: <bucket_name>/<object_name>")
                # extract_frames(video_file.name, frequency)
                #Trigger DAG with file and language as parameters
                airflow_url = os.environ.get('AIRFLOW_URL')
                headers = {
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "Authorization": os.environ.get('AIRFLOW_AUTH'),
                }
                json_data = {"conf" : {"video_title": video_file.name, "frequency": frequency}}
                response = requests.post(airflow_url, headers=headers, json=json_data)
                if response.status_code == 200:
                    response_json = response.json()
                    st.write(
                        "DAG triggered successfully",
                        response_json["execution_date"],
                        response_json["dag_run_id"],
                    )
                else:
                    st.write(f"Error triggering DAG: {response.text}", None, None)
        else:
            # Process the YouTube video URL
            get_video_youtube()