import boto3
from datetime import datetime
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from dotenv import load_dotenv
import os
from airflow.models import Variable
import requests
import re
from moviepy.editor import *
from PIL import Image
import replicate


# Create a Polly client object
pollyclient = boto3.client('polly', region_name=Variable.get('AWS_REGION'), aws_access_key_id=Variable.get('AWS_ACCESS_KEY'), aws_secret_access_key=Variable.get('AWS_SECRET_KEY'))


api_url = Variable.get('SUPER_IMAGE_URL')
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN')
X_RapidAPI_Key = os.environ.get('X_RapidAPI_Key')


load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_KEY')
USER_BUCKET_NAME = Variable.get('USER_BUCKET_NAME')


s3client = boto3.client(
    's3',
    aws_access_key_id=Variable.get('AWS_ACCESS_KEY'),
    aws_secret_access_key=Variable.get('AWS_SECRET_KEY')

)


s3 = boto3.resource('s3', 
                    region_name = 'us-east-1',
                    aws_access_key_id = Variable.get('AWS_ACCESS_KEY'),
                    aws_secret_access_key = Variable.get('AWS_SECRET_KEY')
)




default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 2, 22),
    'retries': 0
}



dag = DAG('video_dag',
          default_args=default_args,
          catchup=False
          )




def display_video():

    # Delete the original file
    response_audio = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='video_input/audio/')
    for obj in response_audio['Contents'][1:]:
        s3client.delete_objects(Bucket=USER_BUCKET_NAME, Delete={'Objects': [{'Key': obj['Key']}]})

    response_image = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='video_input/frames/')
    for obj in response_image['Contents'][1:]:
        if (('.png' or '.jpg') in obj['Key']):
            s3client.delete_objects(Bucket=USER_BUCKET_NAME, Delete={'Objects': [{'Key': obj['Key']}]})




def processed_video(**context):

    videofile = context['ti'].xcom_pull(key='video_file')
    frequency = context['ti'].xcom_pull(key='frequency')

    if frequency=='5sec':
        f=5
    else:
        f=10
    #with st.spinner('Processing video...'):
    final_clip = None
    # Download video file from S3 to local directory
    s3_video_file_name = videofile
    local_video_file_name = videofile
    s3client.download_file(USER_BUCKET_NAME, 'video_input/'+s3_video_file_name + '.mp4', local_video_file_name)

    # Download audio file from S3 to local directory
    response = s3client.list_objects(Bucket=os.environ.get('USER_BUCKET_NAME'), Prefix='video_input/audio/')

    # Get all the wav files and sort them by name
    audio_files = sorted([obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.wav' or '.mp3')])
    
    for i, audio_file in enumerate(audio_files):
        s3client.download_file(USER_BUCKET_NAME, 'video_input/audio/'+str(i)+'.wav', str(i)+'.wav')

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
    s3client.upload_file(local_final_video_file_name, USER_BUCKET_NAME, s3_final_video_file_name)

    # Delete local files
    os.remove(local_video_file_name)
    os.remove(local_final_video_file_name)
    for j in range(0, math.ceil(my_video_2.duration/5)):
        os.remove(str(j)+'.wav')





def processed_audio_from_texts(**context):


    video_file = context['ti'].xcom_pull(key='video_file')
    frequency = context['ti'].xcom_pull(key='frequency')


    # Specify the folder in the input bucket containing the text files
    input_folder_path = 'image_input/text/'
    # Get the list of objects (text files) in the input folder
    objects = s3client.list_objects(Bucket=USER_BUCKET_NAME, Prefix=input_folder_path)
    

    # Set the Polly voice and parameters
    voice_id = 'Joanna'
    output_format = 'mp3'
    engine = 'standard'

    # Iterate through the objects and generate audio for each text file
    for obj in objects['Contents']:
        # Get the text from the object (text file)
        text = s3client.get_object(Bucket=USER_BUCKET_NAME, Key=obj['Key'])['Body'].read().decode('utf-8')
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
            s3client.put_object(Body=response['AudioStream'].read(), Bucket=USER_BUCKET_NAME, Key=audio_file_name)
            s3client.delete_object(Bucket=USER_BUCKET_NAME, Key=file_path)

   
    context['ti'].xcom_push(key='video_file', value=video_file)
    context['ti'].xcom_push(key='frequency', value=frequency)
 




def frame_captioning(**context):

    video_file = context['ti'].xcom_pull(key='video_file')
    frequency = context['ti'].xcom_pull(key='frequency')

    # use the list_objects_v2 function to get a list of all objects in the bucket
    response = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='video_input/frames/')

    file_list = []

    # print the object keys
    for obj in response['Contents']:
        if obj['Key'] != 'video_input/frames/':
            file_list.append(obj['Key'])

    # Define a function to extract the numerical value from the filename
    def get_num_from_filename(filename):
        return int(filename.split("/")[-1].split(".")[0])

    # Sort the list based on the numerical value in the filename
    file_list.sort(key=get_num_from_filename)

    i = 0

    for obj in file_list:
        url = s3client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': USER_BUCKET_NAME,
                    'Key': obj
                },
                ExpiresIn=3600)

        output = replicate.run(
                "rmokady/clip_prefix_caption:9a34a6339872a03f45236f114321fb51fc7aa8269d38ae0ce5334969981e4cd8",
                input={"image": url}
            )
        
        filename = f"{i}.txt"
        with open(filename, "w") as f:
            f.write(output)

        i += 1
                
        # Upload the file to S3
        s3client.upload_file(filename, USER_BUCKET_NAME, f"video_input/text/{filename}")

        os.remove(filename)

    context['ti'].xcom_push(key='video_file', value=video_file)
    context['ti'].xcom_push(key='frequency', value=frequency)
 








def frame_unblurring(**context):


    video_file = context['ti'].xcom_pull(key='video_file')
    frequency = context['ti'].xcom_pull(key='frequency')


    # use the list_objects_v2 function to get a list of all objects in the bucket
    response = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='video_input/frames/')

    file_list = []

    # print the object keys
    for obj in response['Contents']:
        if obj['Key'] != 'video_input/frames/':
            file_list.append(obj['Key'])

    # Define a function to extract the numerical value from the filename
    def get_num_from_filename(filename):
        return int(filename.split("/")[-1].split(".")[0])

    # Sort the list based on the numerical value in the filename
    file_list.sort(key=get_num_from_filename)

    for obj in file_list:
        url = s3client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': USER_BUCKET_NAME,
            'Key': obj
        },
        ExpiresIn=3600)

        print(url)

        payload = {
            "upscale": 2,
            "image": url
        }
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": Variable.get("X_RapidAPI_Key"),
            "X-RapidAPI-Host": Variable.get("X_RapidAPI_Host")
        }

        response = requests.request("POST", api_url, json=payload, headers=headers)

        # print(response)

        output_url = response.json()
        # print(output_url)
        if 'msg' not in output_url:
            output_url = response.json()['output_url']
            image_data = requests.get(output_url).content
            # st.write(type(image_data))
            # st.image(image_data)
        else:
            continue

        # print(output_url)
        s3.Bucket(USER_BUCKET_NAME).put_object(Key=obj, Body=image_data)


    context['ti'].xcom_push(key='video_file', value=video_file)
    context['ti'].xcom_push(key='frequency', value=frequency)



def extract_frames(**context):

    video_file = context['dag_run'].conf['video_title']
    frequency = context['dag_run'].conf['frequency']

    if frequency=='5sec':
        f=5
    else:
        f=10
    # with st.spinner('Extracting frames from video...'):
    video_file=video_file.replace('.mp4', '')
    s3client.download_file(USER_BUCKET_NAME, 'video_input/'+video_file + '.mp4', video_file)
    clip = VideoFileClip(video_file)

    video_duration = clip.duration
    for i in range (0, int(video_duration), f):
        clip.save_frame(str(int(i/f))+'.png', i)
        s3client.upload_file(str(int(i/f))+'.png', USER_BUCKET_NAME, 'video_input/frames/' + str(int(i/f)) + '.png')
        os.remove(str(int(i/f))+'.png')
    
    os.remove(video_file)

    context['ti'].xcom_push(key='video_file', value=video_file)
    context['ti'].xcom_push(key='frequency', value=frequency)







with dag:
    extract = PythonOperator(
        task_id='extract_frames',
        python_callable=extract_frames,
        dag=dag
    )

    unblur = PythonOperator(
        task_id='frame_unblurring',
        python_callable=frame_unblurring,
        dag=dag
    )

    captioning = PythonOperator(
        task_id='frame_captioning',
        python_callable=frame_captioning,
        dag=dag
    )

    text_audio = PythonOperator(
        task_id='processed_audio_from_texts',
        python_callable=processed_audio_from_texts,
        dag=dag

        #chnage the function name
    )

    processed = PythonOperator(
        task_id='processed_video',
        python_callable=processed_video,
        dag=dag
    )

    display = PythonOperator(
        task_id='display_video',
        python_callable=display_video,
        dag=dag
    )

extract >> unblur
unblur >> captioning
captioning >> text_audio
text_audio >> processed
processed >> display
