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
            # Full SQL script to create all tables, indexes, and triggers
            full_sql = """
            -- Create users table with pre-generated content
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INTEGER,
                gender VARCHAR(50),
                image_url TEXT,
                voice_id VARCHAR(255),
                caricature_url TEXT,
                talking_photo_url TEXT,
                face_opts TEXT,
                
                -- Pre-generated Module 1 content (Fake News)
                lottery_faceswap_url TEXT,
                lottery_video_url TEXT,
                crime_faceswap_url TEXT,
                crime_video_url TEXT,
                
                -- Pre-generated Module 2 content (Identity Theft)
                investment_call_audio_url TEXT,
                accident_call_audio_url TEXT,
                
                -- Pre-generated Narrations (JSON object with script_id -> audio_url mapping)
                narration_urls JSONB DEFAULT '{}'::jsonb,
                
                -- Pre-generation status tracking
                pre_generation_status VARCHAR(50) DEFAULT 'pending',
                pre_generation_started_at TIMESTAMP WITH TIME ZONE,
                pre_generation_completed_at TIMESTAMP WITH TIME ZONE,
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
    # HYBRID STRATEGY METHODS
    # ===================================================================================
    
    # Narration Cache Operations
    async def get_narration_cache(self, user_id: int, step_id: str, script_hash: str):
        """Get cached narration for user and step"""
        try:
            result = self.client.table('narration_cache').select("*").eq('user_id', user_id).eq('step_id', step_id).eq('script_hash', script_hash).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error getting narration cache: {e}")
            return None
    
    async def create_narration_cache(self, cache_data: dict):
        """Create new narration cache entry"""
        try:
            result = self.client.table('narration_cache').insert(cache_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error creating narration cache: {e}")
            raise
    
    async def update_narration_cache_access(self, cache_id: int):
        """Update access count and timestamp for cache entry"""
        try:
            from datetime import datetime
            update_data = {
                'access_count': 'access_count + 1',
                'last_accessed_at': datetime.now().isoformat()
            }
            result = self.client.table('narration_cache').update(update_data).eq('id', cache_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error updating narration cache access: {e}")
    
    async def delete_narration_cache(self, cache_id: int):
        """Delete expired cache entry"""
        try:
            result = self.client.table('narration_cache').delete().eq('id', cache_id).execute()
            return True
        except Exception as e:
            print(f"❌ Error deleting narration cache: {e}")
            return False
    
    async def cleanup_expired_narration_cache(self):
        """Clean up expired cache entries"""
        try:
            from datetime import datetime
            result = self.client.table('narration_cache').delete().lt('expires_at', datetime.now().isoformat()).execute()
            return len(result.data) if result.data else 0
        except Exception as e:
            print(f"❌ Error cleaning up expired cache: {e}")
            return 0
    
    # Scenario Generation Job Operations
    async def create_scenario_job(self, job_data: dict):
        """Create new scenario generation job"""
        try:
            result = self.client.table('scenario_generation_jobs').insert(job_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error creating scenario job: {e}")
            raise
    
    async def update_scenario_job(self, job_id: int, update_data: dict):
        """Update scenario generation job status"""
        try:
            result = self.client.table('scenario_generation_jobs').update(update_data).eq('id', job_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"❌ Error updating scenario job: {e}")
            raise
    
    async def get_scenario_jobs(self, user_id: int):
        """Get all scenario jobs for user"""
        try:
            result = self.client.table('scenario_generation_jobs').select("*").eq('user_id', user_id).execute()
            return result.data or []
        except Exception as e:
            print(f"❌ Error getting scenario jobs: {e}")
            return []
    
    # Cache Statistics
    async def get_narration_cache_stats(self, user_id: int):
        """Get cache statistics for user"""
        try:
            result = self.client.table('narration_cache').select("*").eq('user_id', user_id).execute()
            cache_entries = result.data or []
            
            from datetime import datetime
            now = datetime.now()
            
            active_count = sum(1 for entry in cache_entries if entry.get('expires_at') and datetime.fromisoformat(entry['expires_at'].replace('Z', '+00:00')) > now)
            total_access = sum(entry.get('access_count', 0) for entry in cache_entries)
            
            return {
                'total_cached': len(cache_entries),
                'active_cached': active_count,
                'expired_cached': len(cache_entries) - active_count,
                'total_access_count': total_access,
                'cache_hit_rate': min(1.0, total_access / max(1, len(cache_entries)))
            }
        except Exception as e:
            print(f"❌ Error getting cache stats: {e}")
            return {}
    
    async def get_user_narration_cache(self, user_id: int):
        """Get all narration cache entries for user"""
        try:
            result = self.client.table('narration_cache').select("*").eq('user_id', user_id).execute()
            return result.data or []
        except Exception as e:
            print(f"❌ Error getting user narration cache: {e}")
            return []
    
    async def clear_user_narration_cache(self, user_id: int):
        """Clear all cache entries for user"""
        try:
            result = self.client.table('narration_cache').delete().eq('user_id', user_id).execute()
            return len(result.data) if result.data else 0
        except Exception as e:
            print(f"❌ Error clearing user cache: {e}")
            return 0

# Note: SupabaseService is now instantiated directly in main.py