import os
import sys
from google import genai
from google.genai import types

# Run the Google Drive API test
from src.utils.google_drive_utils import test_google_drive_api
from src.utils.api_utils import get_safety_settings
from src.generators.story_generator import retry_story_generation

# Test Google Drive API
print("\n--- Testing Google Drive API Integration ---")
api_test_result = test_google_drive_api()
if not api_test_result:
    print("⚠️ Warning: Google Drive API test failed. Some features related to Google Drive may not work properly.")
else:
    print("✅ Google Drive API integration is ready to use.")

# Set API Key
# IMPORTANT: Set your API key here or as an environment variable
os.environ['GEMINI_API_KEY'] = "AIzaSyDVmSA9ricHVEzo6v1gj-crkuaJvQD72yw"  # Replace with your actual API key

# Check API Key
api_key_check = os.environ.get("GEMINI_API_KEY")
if not api_key_check:
    print("🛑 ERROR: Environment variable GEMINI_API_KEY is not set.")
    print("💡 TIP: Uncomment and set your API key above, or run this in a cell before running this script:")
    print("    os.environ['GEMINI_API_KEY'] = 'YOUR_API_KEY_HERE'")
    raise ValueError("API Key not found in environment.")
else:
    print(f"✅ Found API Key: ...{api_key_check[-4:]}")

# Define Safety Settings
safety_settings = get_safety_settings()
print(f"⚙️ Defined Safety Settings: {safety_settings}")

# Run the story generation process
print("--- Starting generation (attempting 16:9 via prompt) ---")
# You can set use_prompt_generator=True to enable the prompt generator model
# You can also customize the prompt_input to guide the prompt generator
retry_story_generation(use_prompt_generator=True)
print("--- Generation function finished ---")
