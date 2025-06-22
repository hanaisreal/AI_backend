#!/usr/bin/env python3

"""
Simple script to manually trigger scenario generation for a user to test
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Add the api directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

load_dotenv()

async def simple_scenario_generation():
    try:
        from api.supabase_service import SupabaseService
        
        print("🚀 Simple scenario generation test...")
        
        # Initialize services
        supabase_service = SupabaseService()
        
        # Get the most recent user for testing
        result = supabase_service.client.table('users').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not result.data:
            print("❌ No users found in database")
            return
            
        user = result.data[0]
        user_id = user['id']
        print(f"👤 Testing with user: {user['name']} (ID: {user_id})")
        
        # Manual simulation of what should happen:
        # 1. Update user status to in_progress
        print("📝 Updating user status to in_progress...")
        supabase_service.update_user(user_id, {'pre_generation_status': 'in_progress'})
        
        # 2. Simulate generating face swaps (in real implementation these would call APIs)
        print("🎭 Simulating face swap generation...")
        mock_urls = {
            'lottery_faceswap_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/lottery_faceswap_mock.jpg',
            'crime_faceswap_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/crime_faceswap_mock.jpg',
            'lottery_video_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/lottery_video_mock.mp4',
            'crime_video_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/crime_video_mock.mp4',
            'investment_call_audio_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/investment_audio_mock.mp3',
            'accident_call_audio_url': 'https://d3srmxrzq4dz1v.cloudfront.net/pre-generated/accident_audio_mock.mp3'
        }
        
        # 3. Update user with generated URLs
        print("💾 Updating user with mock generated URLs...")
        update_data = mock_urls.copy()
        update_data['pre_generation_status'] = 'completed'
        
        supabase_service.update_user(user_id, update_data)
        
        # 4. Verify the update worked
        updated_user = supabase_service.get_user(user_id)
        
        print("\n✅ User updated successfully!")
        print(f"   Pre-generation Status: {updated_user.get('pre_generation_status')}")
        print("   Generated URLs:")
        for key, url in mock_urls.items():
            if updated_user.get(key):
                print(f"     {key}: ✅")
            else:
                print(f"     {key}: ❌")
                
    except Exception as e:
        print(f"❌ Error in simple test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(simple_scenario_generation())