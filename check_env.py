#!/usr/bin/env python3
"""
Check environment variables for Supabase and other services
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_env_vars():
    print("🔍 Checking Environment Variables...")
    print("=" * 50)
    
    # Supabase variables
    print("📊 SUPABASE CONFIGURATION:")
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    print(f"  SUPABASE_URL: {'✅ SET' if supabase_url else '❌ NOT SET'}")
    if supabase_url:
        print(f"    Value: {supabase_url[:50]}..." if len(supabase_url) > 50 else f"    Value: {supabase_url}")
    
    print(f"  SUPABASE_KEY: {'✅ SET' if supabase_key else '❌ NOT SET'}")
    if supabase_key:
        print(f"    Value: {supabase_key[:20]}...{supabase_key[-10:]}" if len(supabase_key) > 30 else f"    Value: {supabase_key}")
    
    print()
    
    # AWS S3 variables
    print("🗄️ AWS S3 CONFIGURATION:")
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    s3_bucket = os.getenv('S3_BUCKET_NAME')
    aws_region = os.getenv('AWS_REGION')
    cloudfront_domain = os.getenv('CLOUDFRONT_DOMAIN')
    
    print(f"  AWS_ACCESS_KEY_ID: {'✅ SET' if aws_access_key else '❌ NOT SET'}")
    print(f"  AWS_SECRET_ACCESS_KEY: {'✅ SET' if aws_secret_key else '❌ NOT SET'}")
    print(f"  S3_BUCKET_NAME: {'✅ SET' if s3_bucket else '❌ NOT SET'}")
    if s3_bucket:
        print(f"    Value: {s3_bucket}")
    print(f"  AWS_REGION: {'✅ SET' if aws_region else '❌ NOT SET'}")
    if aws_region:
        print(f"    Value: {aws_region}")
    print(f"  CLOUDFRONT_DOMAIN: {'✅ SET' if cloudfront_domain else '❌ NOT SET'}")
    if cloudfront_domain:
        print(f"    Value: {cloudfront_domain}")
    
    print()
    
    # API Keys
    print("🔑 API KEYS:")
    elevenlabs_key = os.getenv('ELEVENLABS_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    akool_client_id = os.getenv('AKOOL_CLIENT_ID')
    akool_client_secret = os.getenv('AKOOL_CLIENT_SECRET')
    
    print(f"  ELEVENLABS_API_KEY: {'✅ SET' if elevenlabs_key else '❌ NOT SET'}")
    print(f"  OPENAI_API_KEY: {'✅ SET' if openai_key else '❌ NOT SET'}")
    print(f"  AKOOL_CLIENT_ID: {'✅ SET' if akool_client_id else '❌ NOT SET'}")
    print(f"  AKOOL_CLIENT_SECRET: {'✅ SET' if akool_client_secret else '❌ NOT SET'}")
    
    print()
    
    # Summary
    print("📋 SUMMARY:")
    all_vars = [
        ('Supabase URL', supabase_url),
        ('Supabase Key', supabase_key),
        ('AWS Access Key', aws_access_key),
        ('AWS Secret Key', aws_secret_key),
        ('S3 Bucket', s3_bucket),
        ('ElevenLabs Key', elevenlabs_key),
        ('OpenAI Key', openai_key),
        ('Akool Client ID', akool_client_id),
        ('Akool Client Secret', akool_client_secret)
    ]
    
    missing = [name for name, value in all_vars if not value]
    
    if missing:
        print(f"❌ Missing {len(missing)} environment variable(s):")
        for var in missing:
            print(f"   - {var}")
    else:
        print("✅ All environment variables are set!")
    
    print("=" * 50)
    
    return len(missing) == 0

if __name__ == "__main__":
    success = check_env_vars()
    if not success:
        print("\n💡 Create a .env file in the backend directory with the missing variables")
    exit(0 if success else 1)