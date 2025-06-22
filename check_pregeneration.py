#!/usr/bin/env python3

"""
Script to check scenario pre-generation status for users
"""

import os
import sys
from dotenv import load_dotenv

# Add the api directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

load_dotenv()

try:
    from api.supabase_service import SupabaseService
    
    print("🔍 Checking scenario pre-generation status...")
    
    # Initialize Supabase service
    supabase_service = SupabaseService()
    
    # Get all users
    result = supabase_service.client.table('users').select('*').execute()
    users = result.data
    
    print(f"\n📊 Found {len(users)} users:")
    
    for user in users:
        print(f"\n👤 User ID: {user['id']}")
        print(f"   Name: {user['name']}")
        print(f"   Gender: {user['gender']}")
        print(f"   Created: {user['created_at']}")
        print(f"   Pre-generation Status: {user.get('pre_generation_status', 'not_set')}")
        
        # Check pre-generated URLs
        pre_generated_urls = {
            'Lottery Faceswap': user.get('lottery_faceswap_url'),
            'Crime Faceswap': user.get('crime_faceswap_url'), 
            'Lottery Video': user.get('lottery_video_url'),
            'Crime Video': user.get('crime_video_url'),
            'Investment Audio': user.get('investment_call_audio_url'),
            'Accident Audio': user.get('accident_call_audio_url')
        }
        
        print("   Pre-generated Content:")
        for content_type, url in pre_generated_urls.items():
            status = "✅ Generated" if url else "❌ Missing"
            print(f"     {content_type}: {status}")
            if url:
                print(f"       URL: {url[:60]}..." if len(url) > 60 else f"       URL: {url}")
        
        if user.get('pre_generation_error'):
            print(f"   ⚠️ Error: {user['pre_generation_error']}")
    
    # Check scenario generation jobs table
    try:
        jobs_result = supabase_service.client.table('scenario_generation_jobs').select('*').execute()
        jobs = jobs_result.data
        
        print(f"\n🛠️ Found {len(jobs)} scenario generation jobs:")
        
        for job in jobs:
            print(f"\n🔧 Job ID: {job['id']}")
            print(f"   User ID: {job['user_id']}")
            print(f"   Job Type: {job['job_type']}")
            print(f"   Job Key: {job['job_key']}")
            print(f"   Status: {job['status']}")
            print(f"   Created: {job['created_at']}")
            if job.get('result_url'):
                print(f"   Result URL: {job['result_url'][:60]}..." if len(job['result_url']) > 60 else f"   Result URL: {job['result_url']}")
            if job.get('error_message'):
                print(f"   ⚠️ Error: {job['error_message']}")
                
    except Exception as e:
        print(f"\n⚠️ Could not check scenario generation jobs: {e}")
        print("   (This table might not exist yet)")

except Exception as e:
    print(f"❌ Error: {e}")
    print("\nMake sure:")
    print("1. Supabase credentials are set in .env")
    print("2. The database tables exist")
    print("3. You have the required Python packages installed")