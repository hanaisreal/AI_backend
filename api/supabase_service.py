import os
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from dotenv import load_dotenv
import json

load_dotenv()

class SupabaseService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    def create_tables(self):
        """Create the necessary tables in Supabase using SQL queries"""
        try:
            # Full SQL script to create all tables, indexes, and triggers
            full_sql = """
            -- Create users table
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INTEGER,
                gender VARCHAR(50),
                image_url TEXT,
                voice_id VARCHAR(255),
                caricature_url TEXT,
                talking_photo_url TEXT,
                current_page VARCHAR(100),
                current_step INTEGER DEFAULT 0,
                completed_modules JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Create quiz_answers table
            CREATE TABLE IF NOT EXISTS quiz_answers (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                module VARCHAR(255),
                answers JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Create indexes for better performance
            CREATE INDEX IF NOT EXISTS idx_users_voice_id ON users(voice_id);
            CREATE INDEX IF NOT EXISTS idx_quiz_answers_user_id ON quiz_answers(user_id);
            CREATE INDEX IF NOT EXISTS idx_quiz_answers_module ON quiz_answers(module);

            -- Create updated_at trigger function
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';

            -- Create triggers to automatically update updated_at column
            DROP TRIGGER IF EXISTS update_users_updated_at ON users;
            CREATE TRIGGER update_users_updated_at 
                BEFORE UPDATE ON users 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            DROP TRIGGER IF EXISTS update_quiz_answers_updated_at ON quiz_answers;
            CREATE TRIGGER update_quiz_answers_updated_at 
                BEFORE UPDATE ON quiz_answers 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            """
            
            # Execute the full SQL script
            result = self.client.rpc('exec_sql', {'sql': full_sql}).execute()
            print("✅ Database tables, indexes, and triggers created successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error creating tables: {e}")
            # Try individual table creation as fallback
            try:
                print("🔄 Trying individual table creation...")
                
                # Try creating tables using Supabase client methods
                # This is a fallback if RPC doesn't work
                print("📝 Note: Please run the SQL script in supabase_schema.sql manually in Supabase dashboard")
                return False
                
            except Exception as e2:
                print(f"❌ Fallback also failed: {e2}")
                raise
    
    # User operations
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        try:
            result = self.client.table('users').insert(user_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            raise
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            result = self.client.table('users').select("*").eq('id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error getting user: {e}")
            return None
    
    def get_user_by_voice_id(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """Get user by voice_id"""
        try:
            result = self.client.table('users').select("*").eq('voice_id', voice_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error getting user by voice_id: {e}")
            return None
    
    def update_user(self, user_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user data"""
        try:
            # Add updated_at timestamp
            update_data['updated_at'] = 'NOW()'
            result = self.client.table('users').update(update_data).eq('id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error updating user: {e}")
            raise
    
    def update_user_progress(self, user_id: int, progress_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user progress"""
        try:
            update_data = {}
            if 'currentPage' in progress_data:
                update_data['current_page'] = progress_data['currentPage']
            if 'currentStep' in progress_data:
                update_data['current_step'] = progress_data['currentStep']
            if 'caricatureUrl' in progress_data:
                update_data['caricature_url'] = progress_data['caricatureUrl']
            if 'talkingPhotoUrl' in progress_data:
                update_data['talking_photo_url'] = progress_data['talkingPhotoUrl']
            if 'completedModules' in progress_data:
                update_data['completed_modules'] = json.dumps(progress_data['completedModules'])
            
            return self.update_user(user_id, update_data)
        except Exception as e:
            print(f"❌ Error updating user progress: {e}")
            raise
    
    # Quiz operations
    def save_quiz_answer(self, user_id: int, module: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Save quiz answers"""
        try:
            quiz_data = {
                'user_id': user_id,
                'module': module,
                'answers': json.dumps(answers)
            }
            result = self.client.table('quiz_answers').insert(quiz_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error saving quiz answer: {e}")
            raise
    
    def get_quiz_answers(self, user_id: int, module: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get quiz answers for a user"""
        try:
            query = self.client.table('quiz_answers').select("*").eq('user_id', user_id)
            if module:
                query = query.eq('module', module)
            result = query.execute()
            return result.data or []
        except Exception as e:
            print(f"❌ Error getting quiz answers: {e}")
            return []
    
    # Health check
    def health_check(self) -> bool:
        """Check if Supabase connection is working"""
        try:
            # Simple connection test - just verify we can authenticate
            # This will work even if no tables exist yet
            tables = self.client.table('information_schema.tables').select('table_name').limit(1).execute()
            return True
        except Exception as e:
            # If that fails, try another basic operation
            try:
                # Try to access the users table, even if it doesn't exist - connection error vs table error
                result = self.client.table('users').select('id').limit(1).execute()
                return True
            except Exception as e2:
                # Check if it's a connection error or just missing table
                if 'does not exist' in str(e2):
                    return True  # Connection works, table just doesn't exist yet
                print(f"❌ Supabase health check failed: {e2}")
                return False

# Global instance
supabase_service = SupabaseService()