#!/usr/bin/env python3

"""
Script to create missing database tables for scenario pre-generation
"""

import os
import sys
from dotenv import load_dotenv

# Add the api directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

load_dotenv()

try:
    from api.supabase_service import SupabaseService
    
    print("🔨 Creating missing database tables...")
    
    # Initialize Supabase service
    supabase_service = SupabaseService()
    
    # SQL to create scenario_generation_jobs table
    create_jobs_table_sql = """
    CREATE TABLE IF NOT EXISTS scenario_generation_jobs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        job_type VARCHAR(100) NOT NULL,
        job_key VARCHAR(100) NOT NULL,
        status VARCHAR(50) DEFAULT 'pending',
        start_time TIMESTAMP WITH TIME ZONE,
        completion_time TIMESTAMP WITH TIME ZONE,
        result_url TEXT,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 2,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """
    
    # SQL to create indexes
    create_indexes_sql = """
    CREATE INDEX IF NOT EXISTS idx_scenario_jobs_user_id ON scenario_generation_jobs(user_id);
    CREATE INDEX IF NOT EXISTS idx_scenario_jobs_status ON scenario_generation_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_scenario_jobs_type ON scenario_generation_jobs(job_type);
    """
    
    # SQL to enable RLS
    enable_rls_sql = """
    ALTER TABLE scenario_generation_jobs ENABLE ROW LEVEL SECURITY;
    """
    
    # SQL to create policy
    create_policy_sql = """
    DROP POLICY IF EXISTS "Allow all operations on scenario_generation_jobs" ON scenario_generation_jobs;
    CREATE POLICY "Allow all operations on scenario_generation_jobs" ON scenario_generation_jobs
        FOR ALL USING (true);
    """
    
    try:
        # Execute table creation
        print("📝 Creating scenario_generation_jobs table...")
        result = supabase_service.client.rpc('exec_sql', {'sql': create_jobs_table_sql}).execute()
        print("✅ Table created successfully")
        
        # Execute indexes
        print("📝 Creating indexes...")
        result = supabase_service.client.rpc('exec_sql', {'sql': create_indexes_sql}).execute()
        print("✅ Indexes created successfully")
        
        # Enable RLS
        print("📝 Enabling RLS...")
        result = supabase_service.client.rpc('exec_sql', {'sql': enable_rls_sql}).execute()
        print("✅ RLS enabled successfully")
        
        # Create policy
        print("📝 Creating policy...")
        result = supabase_service.client.rpc('exec_sql', {'sql': create_policy_sql}).execute()
        print("✅ Policy created successfully")
        
    except Exception as e:
        print(f"⚠️ SQL execution failed: {e}")
        print("\n📋 Please run these SQL commands manually in Supabase SQL Editor:")
        print("\n" + "="*60)
        print(create_jobs_table_sql)
        print(create_indexes_sql) 
        print(enable_rls_sql)
        print(create_policy_sql)
        print("="*60)
    
    # Test the table exists
    try:
        print("\n🔍 Testing table access...")
        result = supabase_service.client.table('scenario_generation_jobs').select('*').limit(1).execute()
        print("✅ scenario_generation_jobs table is accessible")
    except Exception as e:
        print(f"❌ Table not accessible: {e}")

except Exception as e:
    print(f"❌ Error: {e}")