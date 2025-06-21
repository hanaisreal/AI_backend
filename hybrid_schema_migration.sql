-- Hybrid Strategy Database Schema Migration
-- Scenarios pre-generated, narrations just-in-time with caching

-- Add scenario pre-generation fields to existing users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS voice_name VARCHAR(255);

-- Pre-generated face swap images (immediate after caricature)
ALTER TABLE users ADD COLUMN IF NOT EXISTS lottery_faceswap_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS crime_faceswap_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS investment_faceswap_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS accident_faceswap_url TEXT;

-- Pre-generated talking photos (immediate after caricature)
ALTER TABLE users ADD COLUMN IF NOT EXISTS lottery_video_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS crime_video_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS investment_video_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS accident_video_url TEXT;

-- Pre-generated voice dubs (immediate after caricature)
ALTER TABLE users ADD COLUMN IF NOT EXISTS investment_call_audio_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS accident_call_audio_url TEXT;

-- Scenario pre-generation status tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS scenario_generation_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE users ADD COLUMN IF NOT EXISTS scenario_generation_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS scenario_generation_completed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS scenario_generation_error TEXT;

-- Create narration cache table for just-in-time generation
CREATE TABLE IF NOT EXISTS narration_cache (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    step_id VARCHAR(100) NOT NULL,
    script_hash VARCHAR(64) NOT NULL, -- SHA256 hash of script for cache validation
    audio_url TEXT NOT NULL,
    audio_duration INTEGER, -- duration in seconds
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '24 hours'),
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create background jobs table for scenario generation
CREATE TABLE IF NOT EXISTS scenario_generation_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL, -- 'face_swap', 'talking_photo', 'voice_dub'
    job_key VARCHAR(100) NOT NULL, -- specific scenario (e.g., 'lottery_faceswap', 'crime_video')
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, completed, failed
    start_time TIMESTAMP WITH TIME ZONE,
    completion_time TIMESTAMP WITH TIME ZONE,
    result_url TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 2,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_scenario_generation_status ON users(scenario_generation_status);
CREATE INDEX IF NOT EXISTS idx_narration_cache_user_step ON narration_cache(user_id, step_id);
CREATE INDEX IF NOT EXISTS idx_narration_cache_expires ON narration_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_scenario_jobs_user_id ON scenario_generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_scenario_jobs_status ON scenario_generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scenario_jobs_type ON scenario_generation_jobs(job_type);

-- Create trigger for scenario_generation_jobs updated_at
CREATE TRIGGER update_scenario_generation_jobs_updated_at 
    BEFORE UPDATE ON scenario_generation_jobs 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS for new tables
ALTER TABLE narration_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenario_generation_jobs ENABLE ROW LEVEL SECURITY;

-- Create policies for new tables
CREATE POLICY "Allow all operations on narration_cache" ON narration_cache
    FOR ALL USING (true);

CREATE POLICY "Allow all operations on scenario_generation_jobs" ON scenario_generation_jobs
    FOR ALL USING (true);

-- Create cleanup function for expired narration cache
CREATE OR REPLACE FUNCTION cleanup_expired_narration_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM narration_cache 
    WHERE expires_at < NOW();
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Optional: Create scheduled job to cleanup expired cache (if using pg_cron extension)
-- SELECT cron.schedule('cleanup-narration-cache', '0 */6 * * *', 'SELECT cleanup_expired_narration_cache();');