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
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            print(f"✅ Supabase client initialized successfully")
            print(f"   URL: {self.supabase_url}")
            print(f"   Key: {self.supabase_key[:20]}...")
            
            # Test connection
            self.test_connection()
            print("✅ Supabase connection verified")
            
            # Try to initialize tables (optional)
            try:
                self.create_tables()
                print("✅ Supabase tables initialized")
            except Exception as table_error:
                print(f"⚠️ Warning: Could not auto-create tables: {table_error}")
                print("📝 Please run the SQL script manually in Supabase dashboard if tables don't exist")
        except Exception as e:
            print(f"❌ Failed to initialize Supabase client: {e}")
            raise
    
    def test_connection(self):
        """Test the Supabase connection"""
        try:
            # Simple test query to verify connection
            result = self.client.table('information_schema.tables').select('table_name').limit(1).execute()
            return True
        except Exception as e:
            # If the above fails, try a different approach
            try:
                # Try to access any table - this will fail gracefully if no connection
                result = self.client.table('users').select('id').limit(1).execute()
                return True
            except Exception as e2:
                if 'does not exist' in str(e2).lower():
                    # Connection works, table just doesn't exist
                    return True
                else:
                    # Real connection error
                    raise e2
    
    def create_tables(self):
        """Create the necessary tables in Supabase using SQL queries"""
        try:
            # Simple SQL script to create users table with scenario URLs
            full_sql = """
            -- Create users table with pre-generated scenario content
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INTEGER,
                gender VARCHAR(50),
                image_url TEXT,
                voice_id VARCHAR(255),
                caricature_url TEXT,
                talking_photo_url TEXT,
                
                -- Pre-generated scenario content URLs
                lottery_faceswap_url TEXT,
                lottery_video_url TEXT,
                crime_faceswap_url TEXT,
                crime_video_url TEXT,
                investment_call_audio_url TEXT,
                accident_call_audio_url TEXT,
                
                -- Pre-generation status tracking
                pre_generation_status VARCHAR(50) DEFAULT 'pending',
                pre_generation_error TEXT,
                
                -- User progress tracking
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
            CREATE INDEX IF NOT EXISTS idx_users_image_url ON users(image_url);
            CREATE INDEX IF NOT EXISTS idx_users_pre_generation_status ON users(pre_generation_status);
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
            
            # Try to execute SQL using the built-in sql method
            try:
                result = self.client.sql(full_sql).execute()
                print("✅ Database tables, indexes, and triggers created successfully")
                return True
            except AttributeError:
                # If sql method doesn't exist, try rpc approach
                result = self.client.rpc('exec_sql', {'sql': full_sql}).execute()
                print("✅ Database tables, indexes, and triggers created successfully (via RPC)")
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
            print(f"🔄 BACKEND: Updating user {user_id} progress")
            print(f"   - Raw progress data: {progress_data}")
            
            update_data = {}
            if 'currentPage' in progress_data:
                update_data['current_page'] = progress_data['currentPage']
                print(f"   - Updating current_page: {progress_data['currentPage']}")
            if 'currentStep' in progress_data:
                update_data['current_step'] = progress_data['currentStep']
                print(f"   - Updating current_step: {progress_data['currentStep']}")
            if 'caricatureUrl' in progress_data:
                update_data['caricature_url'] = progress_data['caricatureUrl']
                print(f"   - Updating caricature_url: {progress_data['caricatureUrl']}")
            if 'talkingPhotoUrl' in progress_data:
                update_data['talking_photo_url'] = progress_data['talkingPhotoUrl']
                print(f"   - Updating talking_photo_url: {progress_data['talkingPhotoUrl']}")
            if 'completedModules' in progress_data:
                update_data['completed_modules'] = json.dumps(progress_data['completedModules'])
                print(f"   - Updating completed_modules: {progress_data['completedModules']}")
            
            print(f"   - Final update_data: {update_data}")
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

    # ===================================================================================
    # SIMPLE SCENARIO STATUS METHODS  
    # ===================================================================================
    
    def get_user_scenario_status(self, user_id: int):
        """Get scenario generation status for user (simple version)"""
        try:
            user = self.get_user(user_id)
            if not user:
                return None
                
            return {
                'status': user.get('pre_generation_status', 'pending'),
                'started_at': user.get('pre_generation_started_at'),
                'completed_at': user.get('pre_generation_completed_at'), 
                'error': user.get('pre_generation_error'),
                'urls': {
                    'lottery_faceswap_url': user.get('lottery_faceswap_url'),
                    'crime_faceswap_url': user.get('crime_faceswap_url'),
                    'lottery_video_url': user.get('lottery_video_url'),
                    'crime_video_url': user.get('crime_video_url'),
                    'investment_call_audio_url': user.get('investment_call_audio_url'),
                    'accident_call_audio_url': user.get('accident_call_audio_url')
                }
            }
        except Exception as e:
            print(f"❌ Error getting user scenario status: {e}")
            return None

# Note: SupabaseService is now instantiated directly in main.py