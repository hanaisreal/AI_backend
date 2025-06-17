"""
Script to initialize Supabase tables for the AI Awareness project.
Run this script after setting up your Supabase project and environment variables.
"""
import asyncio
import os
from supabase_service import supabase_service

def init_database():
    """Initialize the database tables in Supabase"""
    print("🚀 Initializing Supabase database...")
    
    # Check connection
    if not supabase_service.health_check():
        print("❌ Failed to connect to Supabase. Please check your environment variables.")
        print("💡 Make sure you have set SUPABASE_URL and SUPABASE_KEY (service role) in your .env file")
        return False
    
    print("✅ Supabase connection successful")
    
    try:
        # Create tables
        success = supabase_service.create_tables()
        if success:
            print("✅ Database initialization completed successfully!")
            return True
        else:
            print("⚠️ Automatic table creation failed. Please run the SQL script manually.")
            print("📝 Copy the content from 'supabase_schema.sql' and run it in your Supabase SQL Editor")
            return False
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("📝 Please run the SQL script manually in Supabase dashboard")
        return False

if __name__ == "__main__":
    success = init_database()
    if not success:
        exit(1)