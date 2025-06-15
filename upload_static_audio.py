#!/usr/bin/env python3
"""
Script to upload the static audio sample to S3 for Akool talking photo generation.
This only needs to be run once to upload the static audio file.
"""

import os
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")

def upload_static_audio():
    """Upload the static audio sample to S3"""
    
    if not all([S3_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION]):
        print("❌ Missing AWS credentials in .env file")
        return None
    
    # Initialize S3 client
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        print("✅ S3 client initialized")
    except Exception as e:
        print(f"❌ Error initializing S3 client: {e}")
        return None
    
    # Audio file paths
    local_audio_path = "../frontend/audio-sample.mp3"
    s3_object_name = "static_audio/korean_sample.mp3"
    
    # Check if local file exists
    if not os.path.exists(local_audio_path):
        print(f"❌ Audio file not found: {local_audio_path}")
        return None
    
    try:
        # Upload to S3
        print(f"📤 Uploading {local_audio_path} to S3...")
        s3_client.upload_file(
            local_audio_path,
            S3_BUCKET_NAME,
            s3_object_name,
            ExtraArgs={
                'ACL': 'public-read',
                'ContentType': 'audio/mpeg',
                'ContentDisposition': 'inline; filename="korean_sample.mp3"'
            }
        )
        
        # Construct public URL
        audio_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_object_name}"
        print(f"✅ Audio uploaded successfully!")
        print(f"🔗 Public URL: {audio_url}")
        
        return audio_url
        
    except Exception as e:
        print(f"❌ Error uploading audio: {e}")
        return None

if __name__ == "__main__":
    print("🎵 Uploading static Korean audio sample for Akool talking photo generation...")
    print("Audio content: '지금부터 제가 설명하는 걸 잘 들어보세요'")
    print()
    
    result = upload_static_audio()
    
    if result:
        print()
        print("🎉 Upload complete! You can now use this URL in the talking photo API.")
        print("💡 Add this URL as a constant in your backend code.")
    else:
        print()
        print("❌ Upload failed. Please check your AWS credentials and try again.")