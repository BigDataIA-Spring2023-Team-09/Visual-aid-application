# Visual-aid Application

## Introduction
This project is undertaken with the goal of building an innovative application that brings the visual world to the visually impaired with automated audio descriptions. We understand that people with visual impairments face significant barriers in accessing visual information, which is essential for understanding the world around them. Vaider aims to break down these barriers by providing audio descriptions for videos and images, making the complete video watching experience more immersive and opening countless learning opportunities.

With innovative technologies such as 'Super Image API' by Sensor AI for image sharpening, 'clip_prefix_caption' for image-to-text descriptions, and 'Amazon Polly' for text-to-voice generation, __Vaider__ offers a seamless solution for visually impaired individuals to understand the context of videos and images. The application allows users to upload a video or image to be analyzed, automatically captures frames at preset time intervals, enhances frame quality, and deduces spatial descriptions using advanced image-captioning models.

Technologies used in this project
* Streamlit
* AWS S3
* Apache Airflow
* Docker
* Google Cloud Platform
* [Amazon Polly](https://docs.aws.amazon.com/polly/latest/dg/what-is.html)
* [Super Image API by Sensor AI](https://rapidapi.com/sensorai-sensorai-default/api/super-image1)
* [clip_prefix_caption](https://replicate.com/rmokady/clip_prefix_caption/api)

## Architecture diagram
![deployment_architecture_diagram](https://user-images.githubusercontent.com/108916132/230794745-119a4a8b-27e9-4521-b351-d90786608375.png)

## Implementation
1. Developed a Streamlit web application that allows users to upload videos or images to the S3 bucket to be processed and view the resulting audio descriptions.
2. Created an AWS S3 bucket to store the videos and images, uploaded by users.
3. Extracted frames from the video, as per user preference, i.e., either every 5sec or 10sec.
4. Used 'Super Image API' by Sensor AI to enhance the quality of these images.
5. Used 'clip_prefix_caption' to generate text descriptions for the sharpened images.
6. Used 'Amazon Polly' to generate audio descriptions from the text descriptions. 
7. Set up an Apache Airflow DAG to check the S3 bucket for new videos or images to be processed, and deployed the application on Google Cloud Platform.
8. By implementing this project, we aimed to create a tool that can help people with visual impairments access visual information and learn more about the world around them.


## Files
```
📦 Visual-aid-application
├─ .gitignore
├─ airflow
│  └─ app
│     └─ dags
│        ├─ image_dag.py
│        └─ video_dag.py
├─ requirements.txt
└─ streamlit
   ├─ Video.py
   └─ pages
      └─ Images.py
```

* <code>image_dag.py</code>: This file contains the DAG implementation logic for processing user images. User can upload images of their choice and the DAG gets fired up with the respective parameters.
* <code>video_dag.py</code>: This DAG is responsible to process videos uploaded by user. User can either feed a Youtube video URL or upload a video from local directory. This DAG processes the uploaded video and displays the enhanced video back to user on Streamlit UI.
* <code>Video.py</code>: This file contains the logic behind the processing of video files. This code was then modified to implement the video DAG. This code is responsible to extract frames from video, trigger external APIs for image processing, and embedd the generated audio descriptions back to the original video.
* <code>Images.py</code>: This file contains the logic behind the processing of image files. This code was then modified to implement the image DAG. This code is responsible for triggering external APIs for image processing, and embedd the generated audio descriptions to the original images, and generate a processed video.
* <code>requirements.txt</code>: Outlines the package requirements needed to run the application.

## Installation

To clone and replicate the repository, please follow the steps below:

1.  Open the command line interface (CLI) on your computer.
2.  Navigate to the directory where you want to clone the repository.
3.  Type `git clone https://github.com/BigDataIA-Spring2023-Team-09/Visual-aid-application.git` and press Enter. This will clone the repository to your local machine.
4.  Navigate into the cloned repository using `cd your-repo`
5.  Set environment variables as mentioned below.
6.  Navigate to 'streamlit' directory and run the command `streamlit run video.py`

#### Environment variables:

* REPLICATE_API_TOKEN = "your_key_here"
* SUPER_IMAGE_URL = "your_key_here"
* X_RapidAPI_Key = "your_key_here"
* X_RapidAPI_Host = "your_key_here"
* AWS_ACCESS_KEY = "your_key_here"
* AWS_SECRET_KEY = "your_key_here"
* USER_BUCKET_NAME =  "your_key_here"
* AWS_REGION =  "your_key_here"
* AIRFLOW_URL_VIDEO = "your_key_here"
* AIRFLOW_URL_IMAGE = "your_key_here"
* AIRFLOW_AUTH = "your_key_here"

## Application public link:
https://bigdataia-spring2023-team-09-visual-aid-a-streamlitvideo-8a5k4o.streamlit.app

## Airflow DAGs:
http://34.74.233.133:8080/

## Codelab document:
https://codelabs-preview.appspot.com/?file_id=176yDlJMSyfDnlYmZfKLIxqioraSpWa4mLdJf1tfkWLc#0

## Attestation:
WE ATTEST THAT WE HAVEN’T USED ANY OTHER STUDENTS’ WORK IN OUR ASSIGNMENT AND ABIDE BY THE POLICIES LISTED IN THE STUDENT HANDBOOK
Contribution:
* Ananthakrishnan Harikumar: 25%
* Harshit Mittal: 25%
* Lakshman Raaj Senthil Nathan: 25%
* Sruthi Bhaskar: 25%
