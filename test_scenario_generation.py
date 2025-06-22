#!/usr/bin/env python3

"""
Script to test scenario pre-generation manually
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Add the api directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

load_dotenv()

async def test_scenario_generation():
    try:
        from api.supabase_service import SupabaseService
        from api.scenario_pregeneration_service import ScenarioPreGenerationService
        
        print("🧪 Testing scenario pre-generation service...")
        
        # Initialize services
        supabase_service = SupabaseService()
        scenario_service = ScenarioPreGenerationService(supabase_service, "http://localhost:8000")
        
        # Get the most recent user for testing
        result = supabase_service.client.table('users').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not result.data:
            print("❌ No users found in database")
            return
            
        user = result.data[0]
        print(f"👤 Testing with user: {user['name']} (ID: {user['id']})")
        print(f"   Image URL: {user['image_url']}")
        print(f"   Voice ID: {user['voice_id']}")
        print(f"   Gender: {user['gender']}")
        
        # Test the scenario pre-generation
        print("\n🚀 Starting scenario pre-generation test...")
        success = await scenario_service.start_scenario_pregeneration(
            user['id'], 
            user['image_url'], 
            user['voice_id'], 
            user['gender']
        )
        
        if success:
            print("✅ Scenario pre-generation started successfully!")
            
            # Wait a bit and check status
            await asyncio.sleep(5)
            
            # Check jobs created
            jobs_result = supabase_service.client.table('scenario_generation_jobs').select('*').eq('user_id', user['id']).execute()
            jobs = jobs_result.data
            
            print(f"\n📊 Found {len(jobs)} jobs created:")
            for job in jobs:
                print(f"   - {job['job_type']}: {job['job_key']} ({job['status']})")
                
            # Check user status
            updated_user = supabase_service.get_user(user['id'])
            print(f"\n👤 User pre-generation status: {updated_user.get('pre_generation_status', 'not_set')}")
            
        else:
            print("❌ Scenario pre-generation failed to start")
            
    except Exception as e:
        print(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scenario_generation())