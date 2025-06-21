#!/usr/bin/env python3
"""
Test script to verify hybrid imports work correctly
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_hybrid_imports():
    print("🔍 Testing hybrid service imports...")
    
    try:
        # Test individual module imports
        print("  - Testing hybrid_models import...")
        from api.hybrid_models import SmartNarrationRequest, SmartNarrationResponse
        print("    ✅ hybrid_models imported successfully")
        
        print("  - Testing hybrid_api_endpoints import...")
        from api.hybrid_api_endpoints import initialize_hybrid_services
        print("    ✅ hybrid_api_endpoints imported successfully")
        
        print("  - Testing scenario_pregeneration_service import...")
        from api.scenario_pregeneration_service import ScenarioPreGenerationService
        print("    ✅ scenario_pregeneration_service imported successfully")
        
        print("  - Testing smart_narration_service import...")
        from api.smart_narration_service import SmartNarrationService
        print("    ✅ smart_narration_service imported successfully")
        
        # Test model instantiation
        print("  - Testing SmartNarrationRequest instantiation...")
        request = SmartNarrationRequest(
            user_id=1,
            step_id="test",
            current_script="test script",
            voice_id="test_voice"
        )
        print(f"    ✅ SmartNarrationRequest created: {request.user_id}")
        
        print("\n🎉 All hybrid imports successful!")
        return True
        
    except ImportError as e:
        print(f"    ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"    ❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_hybrid_imports()
    sys.exit(0 if success else 1)