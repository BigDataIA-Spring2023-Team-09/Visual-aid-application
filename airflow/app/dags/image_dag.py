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

api_url = os.environ.get('SUPER_IMAGE_URL')
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN')


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
                    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY'),
                    aws_secret_access_key = os.environ.get('AWS_SECRET_KEY')
)




default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 2, 22),
    'retries': 0
}



dag = DAG('image_dag',
          default_args=default_args,
          catchup=False
          )



def display_video_from_images():
    video_stream = s3client.get_object(Bucket=USER_BUCKET_NAME, Key='video_output/' + 'video_from_images.mp4')['Body'].read()

    # # Stream the video using st.video()
    # st.video(video_stream, start_time=0)

    # Delete the original file
    response_audio = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/audio/')
    for obj in response_audio['Contents'][1:]:
        s3client.delete_objects(Bucket=USER_BUCKET_NAME, Delete={'Objects': [{'Key': obj['Key']}]})

    response_image = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/')
    for obj in response_image['Contents'][1:]:
        if (('.png' or '.jpg') in obj['Key']):
            s3client.delete_objects(Bucket=USER_BUCKET_NAME, Delete={'Objects': [{'Key': obj['Key']}]})





def processed_video_from_images():
    # with st.spinner('Processing the images...'):
    image_files=[]
    audio_files=[]
    final_clip = None

    # List of image and audio files
    response_audio = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/audio/')

    for obj in response_audio['Contents'][1:]:
        filename_audio=obj['Key'].replace('image_input/audio/', '')
        s3client.download_file(USER_BUCKET_NAME, 'image_input/audio/'+f'{filename_audio}', f'{filename_audio}')
        audio_files.append(filename_audio)

    response_image = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/')

    for obj in response_image['Contents'][1:]:
        filename_image=obj['Key'].replace('image_input/', '')
        if (('.png' or '.jpg') in filename_image):
            s3client.download_file(USER_BUCKET_NAME, 'image_input/'+f'{filename_image}', f'{filename_image}')
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
        s3client.upload_file('video_from_images.mp4', USER_BUCKET_NAME, 'video_output/'+'video_from_images.mp4')

        # Delete local files
        os.remove('video_from_images.mp4')
        for j in range(len(image_files)):
            os.remove(image_files[j])
            os.remove(audio_files[j])
    



def processed_audio_from_texts():
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





def image_captioning():
# use the list_objects_v2 function to get a list of all objects in the bucket
    response = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/')

    file_list = []

    # print the object keys
    for obj in response['Contents']:
        if obj['Key'] != 'image_input/' and '/text/' not in obj['Key'] and '/audio/' not in obj['Key']:
            file_list.append(obj['Key'])

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
            
        filename = obj.split('/')[-1].replace('.jpg', '.txt').replace('.jpeg', '.txt').replace('.png', '.txt')

        with open(filename, "w") as f:
            f.write(output)
                
        # Upload the file to S3
        s3client.upload_file(filename, USER_BUCKET_NAME, f"image_input/text/{filename}")

        os.remove(filename)




def image_unblurring():


    # use the list_objects_v2 function to get a list of all objects in the bucket
    response = s3client.list_objects_v2(Bucket=USER_BUCKET_NAME, Prefix='image_input/')

    file_list = []

    # print the object keys
    for obj in response['Contents'][1:]:
        if obj['Key'] != 'image_input/' and obj['Key'][-1] != '/' and '/text/' not in obj['Key']:
            file_list.append(obj['Key'])

    for obj in file_list:
        url = s3client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': USER_BUCKET_NAME,
            'Key': obj
        },
        ExpiresIn=3600)


        payload = {
            "upscale": 2,
            "image": url
        }
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": os.environ.get("X_RapidAPI_Key"),
            "X-RapidAPI-Host": os.environ.get("X_RapidAPI_Host")
        }

        response = requests.request("POST", api_url, json=payload, headers=headers)


        output_url = response.json()
        if 'msg' not in output_url:
            output_url = response.json()['output_url']
            image_data = requests.get(output_url).content

        else:
            # delete the file
            s3.Object(USER_BUCKET_NAME, obj).delete()
            continue

        s3.Bucket(USER_BUCKET_NAME).put_object(Key=obj, Body=image_data)








with dag:

    unblur = PythonOperator(
        task_id='image_unblurring',
        python_callable=image_unblurring,
        dag=dag
    )

    captioning = PythonOperator(
        task_id='image_captioning',
        python_callable=image_captioning,
        dag=dag
    )

    text_audio = PythonOperator(
        task_id='processed_audio_from_texts',
        python_callable=processed_audio_from_texts,
        dag=dag
    )

    processed = PythonOperator(
        task_id='processed_video_from_images',
        python_callable=processed_video_from_images,
        dag=dag
    )

    display = PythonOperator(
        task_id='display_video_from_images',
        python_callable=display_video_from_images,
        dag=dag
    )



unblur >> captioning
captioning >> text_audio
text_audio >> processed
processed >> display