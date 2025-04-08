# 1. Install required libraries
!pip install -q google-generativeai IPython
!pip install -q pillow
!pip install -q google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
!pip install -q kokoro>=0.9.2 soundfile
!apt-get -qq -y install espeak-ng > /dev/null 2>&1

# 2. Import libraries
import os
import re
import json
import mimetypes
import tempfile
import datetime
import base64
import subprocess
import numpy as np
import soundfile as sf
import requests
from google import genai
from google.genai import types # Need types for Content/Part/Config/SafetySetting
from IPython.display import display, Image, Audio, HTML
from PIL import Image as PILImage
from kokoro import KPipeline

# Function to download file from Google Drive by ID
def download_file_from_google_drive(file_id, destination):
    """Downloads a file from Google Drive by its file ID without requiring authentication.
    
    Args:
        file_id: The ID of the file in Google Drive
        destination: The local path where the file should be saved
        
    Returns:
        The path to the downloaded file
    """
    # Create the direct download URL
    url = f"https://drive.google.com/uc?id={file_id}&export=download"
    
    # Make the initial request to get the download link
    session = requests.Session()
    response = session.get(url, stream=True)
    
    # Handle potential confirmation page (for large files)
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            url = f"{url}&confirm={value}"
            response = session.get(url, stream=True)
    
    # Save the file
    with open(destination, 'wb') as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)
    
    return destination

# Function to test Google Drive API functionality
def test_google_drive_api():
    """Tests if Google Drive API credentials are working correctly.
    
    This function will:
    1. Download the credentials file from Google Drive
    2. Test authentication with Google Drive API
    3. Verify basic operations (list files, create folder)
    4. Clean up test resources
    
    Returns:
        True if all tests pass, False otherwise
    """
    print("\n⏳ Testing Google Drive API functionality...")
    temp_dir = tempfile.mkdtemp()
    credentials_file_id = "152LtocR_Lvll37IW3GXJWAowLS02YBF2"
    credentials_file_path = os.path.join(temp_dir, "drive_credentials.json")
    
    try:
        # Step 1: Download credentials
        print("⏳ Downloading Google Drive API credentials...")
        download_file_from_google_drive(credentials_file_id, credentials_file_path)
        
        if not os.path.exists(credentials_file_path):
            print("🛑 Failed to download credentials file")
            return False
        
        print(f"✅ Credentials file downloaded to: {credentials_file_path}")
        
        # Step 2: Test authentication and basic operations
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2 import service_account
            
            # Set up credentials
            credentials = service_account.Credentials.from_service_account_file(
                credentials_file_path,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            
            # Create Drive API service
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Step 3: Test listing files
            print("⏳ Testing Drive API: Listing files...")
            results = drive_service.files().list(
                pageSize=5, fields="nextPageToken, files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            print(f"✅ Successfully listed {len(files)} files in Drive")
            
            # Step 4: Test creating a folder
            print("⏳ Testing Drive API: Creating a test folder...")
            test_folder_name = f"test_folder_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            folder_metadata = {
                'name': test_folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = drive_service.files().create(
                body=folder_metadata, fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            print(f"✅ Successfully created test folder: {test_folder_name} (ID: {folder_id})")
            
            # Step 5: Create a test file
            print("⏳ Testing Drive API: Creating a test file...")
            test_file_path = os.path.join(temp_dir, "test_file.txt")
            with open(test_file_path, 'w') as f:
                f.write("This is a test file for Google Drive API functionality.")
            
            file_metadata = {
                'name': 'test_file.txt',
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(test_file_path, mimetype='text/plain', resumable=True)
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            print(f"✅ Successfully uploaded test file (ID: {file_id})")
            
            # Step 6: Clean up test resources
            print("⏳ Cleaning up test resources...")
            drive_service.files().delete(fileId=file_id).execute()
            drive_service.files().delete(fileId=folder_id).execute()
            print("✅ Successfully cleaned up test resources")
            
            print("\n✅ All Google Drive API tests passed! The credentials are working correctly.")
            return True
            
        except Exception as e:
            print(f"🛑 Authentication or API operation failed: {e}")
            return False
            
    except Exception as e:
        print(f"🛑 Error testing Google Drive API: {e}")
        return False
    finally:
        # Clean up the temporary directory if possible
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass

# Run the test before executing any models
print("\n--- Testing Google Drive API Integration ---")
api_test_result = test_google_drive_api()
if not api_test_result:
    print("⚠️ Warning: Google Drive API test failed. Some features related to Google Drive may not work properly.")
else:
    print("✅ Google Drive API integration is ready to use.")

# 3. --- SET API KEY IN ENVIRONMENT ---
#    Make sure this is done BEFORE running this cell.
#    e.g., os.environ['GEMINI_API_KEY'] = "YOUR_API_KEY_HERE"
# ------------------------------------

# Setting API Key
os.environ['GEMINI_API_KEY'] = "AIzaSyDVmSA9ricHVEzo6v1gj-crkuaJvQD72yw"

# --- Check API Key ---
api_key_check = os.environ.get("GEMINI_API_KEY")
if not api_key_check:
    print("🛑 ERROR: Environment variable GEMINI_API_KEY is not set.")
    print("💡 TIP: Uncomment and set your API key above, or run this in a cell before running this script:")
    print("    os.environ['GEMINI_API_KEY'] = 'YOUR_API_KEY_HERE'")
    raise ValueError("API Key not found in environment.")
else:
    print(f"✅ Found API Key: ...{api_key_check[-4:]}")
#------------------------

# Define Safety Settings
safety_settings = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
]
print(f"⚙️ Defined Safety Settings: {safety_settings}")

# Generate prompt using the thinking model
def generate_prompt(prompt_input="Create a children's story with a different animal character and a unique adventure theme. Be creative with the setting and storyline.", use_streaming=True):
    """
    Generates a story prompt using the gemini-2.0-flash-thinking-exp-01-21 model.

    Args:
        prompt_input: The input instructions for generating the prompt
        use_streaming: Whether to use streaming API or not

    Returns:
        The generated prompt text or None if generation fails
    """
    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        print("✅ Initializing prompt generator client using genai.Client...")
    except Exception as e:
        print(f"🔴 Error initializing prompt generator client: {e}")
        return None

    model = "gemini-2.0-flash-thinking-exp-01-21"

    # Enhanced prompt input to ensure consistent structure with varied content
    enhanced_prompt_input = f"""
    Create a children's story prompt using EXACTLY this format:
    "Generate a story about [animal character] going on an adventure in [setting] in a highly detailed 3d cartoon animation style. For each scene, generate a high-quality, photorealistic image for each scene 3d images **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."

    Replace [animal character] with any animal character (NOT a white baby goat named Pip).
    Replace [setting] with any interesting setting for the adventure.

    Do NOT change any other parts of the structure. Keep the exact beginning and ending exactly as shown.

    Your response should be ONLY the completed prompt with no additional text.

    Original guidance: {prompt_input}
    """

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=enhanced_prompt_input),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
    )

    print(f"ℹ️ Using Prompt Generator Model: {model}")
    print(f"📝 Using Input: {prompt_input}")

    generated_prompt = ""

    try:
        if use_streaming:
            print("⏳ Generating prompt via streaming API...")
            stream = client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            )

            print("--- Prompt Generation Stream ---")
            for chunk in stream:
                try:
                    if hasattr(chunk, 'text') and chunk.text:
                        print(chunk.text, end="")
                        generated_prompt += chunk.text
                except Exception as e:
                    print(f"⚠️ Error processing prompt chunk: {e}")
                    continue
        else:
            print("⏳ Generating prompt via non-streaming API...")
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=generate_content_config,
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        print(part.text)
                        generated_prompt += part.text

        # Clean up the generated prompt to ensure it follows the required structure
        generated_prompt = generated_prompt.strip()

        # Remove any quotes that might be around the generated prompt
        generated_prompt = generated_prompt.strip('"\'')

        # For safety, verify the prompt has the correct structure
        if not generated_prompt.startswith("Generate a story about"):
            # Fallback to a properly structured prompt
            print("⚠️ Generated prompt did not have correct structure, applying formatting fix")
            # Extract character and setting if possible
            parts = re.search(r'about\s+(.*?)\s+going\s+on\s+an\s+adventure\s+in\s+(.*?)(?:\s+in\s+a\s+3d|\.)',
                             generated_prompt, re.IGNORECASE)

            if parts:
                character = parts.group(1)
                setting = parts.group(2)
            else:
                # Default fallback
                character = "a colorful chameleon"
                setting = "a magical forest"

            generated_prompt = f"Generate a story about {character} going on an adventure in {setting} in a highly detailed 3d cartoon animation style. For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."

        # Make sure it ends with the correct format
        if not "For each scene, generate an image" in generated_prompt:
            generated_prompt = re.sub(r'\.\s*$', '', generated_prompt) + ". For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."

        # Ensure the 16:9 aspect ratio requirement is present
        if "16:9" not in generated_prompt:
            generated_prompt = generated_prompt.replace("For each scene, generate an image",
                                      "For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting.")

        print("\n✅ Prompt generation complete.")
        print(f"Final generated prompt: {generated_prompt}")
        return generated_prompt

    except Exception as e:
        print(f"🔴 Error generating prompt: {e}")
        return None

def retry_api_call(retry_function, *args, **kwargs):
    """
    Retries API calls when the Gemini model server is unavailable or encounters errors.

    Args:
        retry_function: The function to retry (either generate_prompt or the model API call)
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of the successful function call, or None after maximum retries
    """
    import time

    max_consecutive_failures = 1000  # Effectively keep trying indefinitely
    retry_delay = 10  # seconds
    attempt = 0

    while attempt < max_consecutive_failures:
        attempt += 1
        try:
            print(f"⏳ API call attempt {attempt}...")
            result = retry_function(*args, **kwargs)

            # For generate function, check if we got story and images
            if retry_function.__name__ == 'generate_content_stream' or retry_function.__name__ == 'generate_content':
                # Success criteria - we need to check the response for both text and images
                if result:
                    # Check if the result contains "**Image Description:**" which indicates
                    # the model generated text descriptions instead of actual images

                    # For non-streaming responses
                    if hasattr(result, 'candidates') and result.candidates:
                        for candidate in result.candidates:
                            if hasattr(candidate, 'content') and candidate.content:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text and "**Image Description:**" in part.text:
                                        print(f"⚠️ Model generated text descriptions instead of images on attempt {attempt}, retrying in {retry_delay} seconds...")
                                        time.sleep(retry_delay)
                                        continue

                    # For streaming responses, we can't easily check the content before consuming the stream
                    # So we'll rely on the subsequent processing to detect this issue

                    print(f"✅ API call successful on attempt {attempt}")
                    return result
                else:
                    print(f"⚠️ API returned empty result on attempt {attempt}, retrying in {retry_delay} seconds...")
            else:
                # For other functions like generate_prompt, just check if result is not None
                if result is not None:
                    print(f"✅ API call successful on attempt {attempt}")
                    return result

        except Exception as e:
            print(f"🔴 API error on attempt {attempt}: {e}")

        print(f"🔄 Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)

    print(f"⚠️ Maximum consecutive failures ({max_consecutive_failures}) reached. Giving up.")
    return None

def retry_story_generation(use_prompt_generator=True, prompt_input="Create a unique children's story with a different animal character, setting, and adventure theme."):
    """
    Persistently retries story generation when image loading fails or JSON errors occur.
    This function will keep retrying every 7 seconds until all conditions are met:
    1. No JSON errors in stream processing
    2. Images are properly loaded
    3. At least 6 story segments are generated
    
    Args:
        use_prompt_generator: Whether to use the prompt generator
        prompt_input: The prompt input to guide story generation
        
    Returns:
        The result of the successful generation
    """
    import time
    import threading
    
    # Set initial state
    success = False
    max_retries = 1000  # Set a reasonable limit
    retry_count = 0
    retry_delay = 7  # Run every 7 seconds as specified
    
    # Create a container for results
    results = {"story_text": None, "image_files": [], "output_path": None, "thumbnail_path": None, "metadata": None}
    
    # Create a global temp directory for flag files
    import tempfile
    import os
    temp_dir = tempfile.mkdtemp()
    
    def check_generation_status():
        # This helper function checks if the generation was successful
        # Based on the presence of images and sufficient story segments
        nonlocal success
        
        if not results["story_text"] or not results["image_files"]:
            return False
        
        # Check if we have at least 6 story segments
        try:
            story_segments = collect_complete_story(results["story_text"], return_segments=True)
            if len(story_segments) < 6:
                print(f"⚠️ Insufficient story segments: {len(story_segments)} (need at least 6)")
                return False
                
            # Check if we have sufficient images
            if len(results["image_files"]) < 6:
                print(f"⚠️ Insufficient images: {len(results['image_files'])} (need at least 6)")
                return False
            
            # NEW: Check if video was successfully generated
            if results["output_path"] and os.path.exists(results["output_path"]):
                print(f"✅ Video successfully generated: {results['output_path']}")
                # Note: We don't need to check for a flag file anymore since we use sys.exit()
                # after successful Google Drive upload
                
            # If we get here, generation was successful
            success = True
            return True
        except Exception as e:
            print(f"⚠️ Error checking generation status: {e}")
            return False
    
    # Define a wrapper function that will capture the results
    def generation_wrapper():
        nonlocal results
        try:
            # Create a clean temporary directory for each attempt
            import tempfile
            import os
            temp_dir = tempfile.mkdtemp()
            
            # Call the main generate function
            print(f"\n🔄 Retry attempt #{retry_count+1} for story generation...")
            print(f"⏳ Starting generation with prompt: {prompt_input[:50]}...")
            
            # This is a wrapper that will call the actual generate function
            # but will capture its outputs for our status checks
            result = generate(use_prompt_generator=use_prompt_generator, prompt_input=prompt_input)
            
            # Capture variables from the generate function's scope if possible
            if 'story_text' in locals() and locals()['story_text']:
                results["story_text"] = locals()['story_text']
            if 'image_files' in locals() and locals()['image_files']:
                results["image_files"] = locals()['image_files']
            if 'output_path' in locals() and locals()['output_path']:
                results["output_path"] = locals()['output_path']
            if 'thumbnail_path' in locals() and locals()['thumbnail_path']:
                results["thumbnail_path"] = locals()['thumbnail_path']
            if 'metadata' in locals() and locals()['metadata']:
                results["metadata"] = locals()['metadata']
                
            # Check if generation was successful
            check_generation_status()
        except Exception as e:
            print(f"⚠️ Error in generation attempt: {e}")
            import traceback
            traceback.print_exc()
    
    # Main retry loop
    while not success and retry_count < max_retries:
        retry_count += 1
        
        # Start generation in current thread (blocking)
        generation_wrapper()
        
        # If successful, break the loop
        if success:
            print(f"✅ Story generation successful after {retry_count} attempts!")
            break
            
        # If not successful, wait and retry
        print(f"⚠️ Generation attempt #{retry_count} failed or incomplete.")
        print(f"🔄 Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)
    
    if not success:
        print(f"⚠️ Maximum retry attempts ({max_retries}) reached without success.")
    
    # Return the results regardless of success state
    # This allows partial results to be used if available
    return results

# Generate function
def generate(use_prompt_generator=True, prompt_input="Create a unique children's story with a different animal character, setting, and adventure theme."):
    # Initialize variables that might be used later
    output_path = None
    story_text = None
    image_files = []

    try:
        client = genai.Client(
             api_key=os.environ.get("GEMINI_API_KEY"),
        )
        print("✅ Initializing client using genai.Client...")
    except AttributeError:
        print("🔴 FATAL ERROR: genai.Client is unexpectedly unavailable.")
        return
    except Exception as e:
        print(f"🔴 Error initializing client: {e}")
        return
    print("✅ Client object created successfully.")

    model = "gemini-2.0-flash-exp-image-generation"

    # --- Modified Prompt ---
    if use_prompt_generator:
        print("🧠 Using prompt generator model first...")
        # Use retry mechanism for generate_prompt
        generated_prompt = retry_api_call(generate_prompt, prompt_input)
        if generated_prompt and generated_prompt.strip():
            prompt_text = generated_prompt
            print("✅ Using AI-generated prompt for story and image creation")
        else:
            print("⚠️ Prompt generation failed or returned empty, using default prompt")
            prompt_text = """Generate a story about a white baby goat named Pip going on an adventure in a farm in a highly detailed 3d cartoon animation style. For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."""
    else:
        prompt_text = """Generate a story about a white baby goat named Pip going on an adventure in a farm in a highly detailed 3d cartoon animation style. For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."""
    # --- End Modified Prompt ---

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt_text),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_modalities=["image", "text"],
        response_mime_type="text/plain",
        safety_settings=safety_settings,
    )

    print(f"ℹ️ Using Model: {model}")
    print(f"📝 Using Prompt: {prompt_text}") # Show the modified prompt
    print(f"⚙️ Using Config (incl. safety): {generate_content_config}")
    print("⏳ Calling client.models.generate_content_stream...")

    try:
        # Create a temporary directory to store images and audio
        temp_dir = tempfile.mkdtemp()

        # Variables to collect story and images
        story_text = ""
        image_files = []

        try:
            # Flag to determine if we should use streaming or fallback approach
            use_streaming = True

            try:
                # Wrap the API call in the retry mechanism
                def attempt_stream_generation():
                    return client.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=generate_content_config,
                    )

                stream = retry_api_call(attempt_stream_generation)

            except json.decoder.JSONDecodeError as je:
                print(f"⚠️ JSON decoding error during stream creation: {je}")
                print("Trying fallback to non-streaming API call...")
                use_streaming = False

                # Fallback to non-streaming version
                try:
                    # Wrap the fallback API call in the retry mechanism
                    def attempt_non_stream_generation():
                        return client.models.generate_content(
                            model=model,
                            contents=contents,
                            config=generate_content_config,
                        )

                    response = retry_api_call(attempt_non_stream_generation)

                    # Process the non-streaming response
                    print("Using non-streaming response instead")
                    image_found = False

                    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                image_found = True
                                inline_data = part.inline_data
                                image_data = inline_data.data
                                mime_type = inline_data.mime_type

                                # Save image to a temporary file
                                img_path = os.path.join(temp_dir, f"image_{len(image_files)}.jpg")
                                with open(img_path, "wb") as f:
                                    f.write(image_data)
                                image_files.append(img_path)

                                print(f"\n\n🖼️ --- Image Received ({mime_type}) ---")
                                display(Image(data=image_data))
                                print("--- End Image ---\n")
                            elif hasattr(part, 'text') and part.text:
                                print(part.text)
                                story_text += part.text

                    # Skip the streaming loop since we already processed the response
                    print("✅ Non-streaming processing complete.")
                    if not image_found:
                        print("⚠️ No images were found in the non-streaming response.")

                    # Continue with audio and video processing
                    image_found = True  # Set this to true to prevent early exit

                except Exception as e:
                    print(f"⚠️ Fallback API call also failed: {e}")
                    return

            except Exception as e:
                print(f"⚠️ Error creating stream: {e}")
                return

            # Only enter the streaming loop if we're using streaming
            if use_streaming:
                image_found = False
                print("--- Response Stream ---")

                # Track JSON parsing errors to decide when to fallback
                json_errors = 0
                max_json_errors = 5  # Allow up to 5 errors before giving up on streaming

                # Check for Image Description text instead of actual images
                contains_image_description = False

                try:
                    for chunk in stream:
                        try:
                            # If we get a raw string instead of parsed content
                            if isinstance(chunk, str):
                                print(chunk, end="")
                                story_text += chunk
                                # Check for image descriptions
                                if "**Image Description:**" in chunk:
                                    contains_image_description = True
                                continue

                            # Check if chunk has candidates
                            if not hasattr(chunk, 'candidates') or not chunk.candidates:
                                # Try to extract as much as possible from the chunk
                                if hasattr(chunk, 'text') and chunk.text:
                                    print(chunk.text, end="")
                                    story_text += chunk.text
                                    # Check for image descriptions
                                    if "**Image Description:**" in chunk.text:
                                        contains_image_description = True
                                continue

                            if not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                                if hasattr(chunk, 'text') and chunk.text:
                                    print(chunk.text, end="")
                                    story_text += chunk.text
                                    # Check for image descriptions
                                    if "**Image Description:**" in chunk.text:
                                        contains_image_description = True
                                continue

                            part = chunk.candidates[0].content.parts[0]

                            if hasattr(part, 'inline_data') and part.inline_data:
                                image_found = True
                                inline_data = part.inline_data
                                image_data = inline_data.data
                                mime_type = inline_data.mime_type

                                # Save image to a temporary file
                                img_path = os.path.join(temp_dir, f"image_{len(image_files)}.jpg")
                                with open(img_path, "wb") as f:
                                    f.write(image_data)
                                image_files.append(img_path)

                                print(f"\n\n🖼️ --- Image Received ({mime_type}) ---")
                                display(Image(data=image_data))
                                print("--- End Image ---\n")
                            elif hasattr(part,'text') and part.text:
                                print(part.text, end="")
                                story_text += part.text
                                # Check for image descriptions
                                if "**Image Description:**" in part.text:
                                    contains_image_description = True
                        except json.decoder.JSONDecodeError as je:
                            print(f"\n⚠️ JSON decoding error in chunk: {je}")
                            json_errors += 1
                            if json_errors >= max_json_errors:
                                print(f"Too many JSON errors ({json_errors}), falling back to non-streaming mode...")
                                # Try to extract any text that might be in the raw response
                                try:
                                    if hasattr(chunk, '_response') and hasattr(chunk._response, 'text'):
                                        raw_text = chunk._response.text
                                        # Extract text content between markdown or code blocks if possible
                                        story_text += re.sub(r'```.*?```', '', raw_text, flags=re.DOTALL)
                                        print(f"Extracted {len(raw_text)} characters from raw response")
                                except Exception:
                                    pass
                                break  # Exit the streaming loop and use the fallback
                            continue  # Skip this chunk and continue with next
                        except Exception as e:
                            print(f"\n⚠️ Error processing chunk: {e}")
                            continue  # Skip this chunk and continue with next
                except Exception as e:
                    print(f"⚠️ Error in stream processing: {e}")
                    # If streaming failed completely, try the non-streaming fallback
                    if not story_text.strip() and json_errors > 0:
                        print("Stream processing failed, trying non-streaming fallback...")
                        try:
                            response = client.models.generate_content(
                                model=model,
                                contents=contents,
                                config=generate_content_config,
                            )

                            if response.candidates and response.candidates[0].content:
                                for part in response.candidates[0].content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        story_text += part.text

                            print("✅ Non-streaming fallback successful")
                        except Exception as fallback_error:
                            print(f"⚠️ Non-streaming fallback also failed: {fallback_error}")
        except Exception as e:
            print(f"⚠️ Error in stream creation: {e}")
            return

        print("\n" + "-"*20)
        if not image_found:
             print("⚠️ No images were found in the stream.")
        print("✅ Stream processing complete.")

        if not image_found or contains_image_description:
            if contains_image_description:
                print("\n⚠️ Model generated text descriptions instead of actual images. Restarting generation...")
                # Restart the entire generation process by recursively calling generate
                return generate(use_prompt_generator=use_prompt_generator, prompt_input=prompt_input)
            elif not image_found:
                print("⚠️ No images were found in the stream.")
        print("✅ Stream processing complete.")

        def collect_complete_story(raw_text, return_segments=False):
            """Collect and clean the complete story text from Gemini's output"""
            try:
                # Split the text into lines
                lines = raw_text.split('\n')
                story_segments = []
                current_segment = ""
                in_story_section = False

                # Debug the raw text content
                print("\n--- Raw Text Debug ---")
                print(f"Raw text length: {len(raw_text)} characters")
                print(f"First 100 chars: {raw_text[:100]}")
                print(f"Total lines: {len(lines)}")

                # Check for various marker patterns
                has_story_markers = any('**Story:**' in line or '**Scene' in line for line in lines)
                has_section_markers = any('## Scene' in line or '# Scene' in line for line in lines)
                has_story_keyword = any('story' in line.lower() for line in lines)

                # First check the strongest pattern - explicit story markers
                if has_story_markers:
                    print("Detected story markers in the text")
                    # Original marker-based parsing logic
                    for line in lines:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue

                        # Skip image prompts - don't include them in the story
                        if '**Image Prompt:**' in line:
                            continue

                        # Check for story section
                        if '**Story:**' in line:
                            in_story_section = True
                            # Get the story text after '**Story:**'
                            story_text = line.split('**Story:**')[1].strip()
                            if story_text:  # If there's text on the same line
                                current_segment = story_text
                        # If we're in a story section and it's not a scene or image marker
                        elif in_story_section and not ('**Scene' in line or '**Image:**' in line):
                            # Add the line to current segment
                            if current_segment:
                                current_segment += ' '
                            current_segment += line.strip('* ')
                        # If we hit a new scene marker
                        elif '**Scene' in line:
                            if current_segment:  # Save current segment if exists
                                story_segments.append(current_segment)
                                current_segment = ""
                            in_story_section = True  # Set to true to collect content from this scene
                            # Extract any text after the scene marker
                            parts = line.split(':', 1)
                            if len(parts) > 1:
                                current_segment = parts[1].strip()
                        # Skip image markers but stay in story section
                        elif '**Image:**' in line:
                            continue
                        # If we're in a story section, collect all text
                        elif in_story_section:
                            if current_segment:  # Add space if we already have content
                                current_segment += ' '
                            current_segment += line.strip('* ')

                # Check for markdown section headers
                elif has_section_markers:
                    print("Detected markdown section markers")
                    for line in lines:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue

                        # Start of a new scene or section
                        if line.startswith('## Scene') or line.startswith('# Scene'):
                            if current_segment:  # Save previous segment
                                story_segments.append(current_segment)
                                current_segment = ""
                            in_story_section = True
                            # Extract any text after the header
                            parts = line.split(':', 1)
                            if len(parts) > 1:
                                current_segment = parts[1].strip()
                        # Skip image prompts and other non-story content
                        elif 'image prompt' in line.lower() or 'image:' in line.lower():
                            continue
                        # If we're in a section, add the text
                        elif in_story_section:
                            if current_segment:
                                current_segment += ' '
                            current_segment += line.strip()

                # If no clear section markers but has story keyword, use paragraph-based approach
                elif has_story_keyword:
                    print("Detected story keyword - using paragraph-based approach")
                    paragraph = ""
                    for line in lines:
                        line = line.strip()

                        # Skip image prompts and obvious non-story lines
                        if 'image prompt' in line.lower() or 'image:' in line.lower():
                            continue

                        # Empty line marks paragraph boundary
                        if not line:
                            if paragraph:
                                story_segments.append(paragraph)
                                paragraph = ""
                            continue

                        # Add to current paragraph
                        if paragraph:
                            paragraph += ' '
                        paragraph += line

                    # Add the last paragraph
                    if paragraph:
                        story_segments.append(paragraph)

                # Last resort - just try to extract anything that looks like a story
                else:
                    print("No clear story structure detected - extracting all text content")
                    # Filter out obvious non-story lines
                    content_lines = []
                    for line in lines:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue

                        # Skip lines that are clearly not story content
                        if line.startswith('```') or line.startswith('Image:') or 'prompt' in line.lower():
                            continue

                        # Skip markdown formatting/headers that are standalone
                        if (line.startswith('#') and len(line) < 30) or (line.startswith('**') and line.endswith('**') and len(line) < 30):
                            continue

                        content_lines.append(line)

                    # Join remaining content and treat as one segment
                    if content_lines:
                        story_segments.append(' '.join(content_lines))

                # Add the last segment if exists (for marker-based parsing)
                if current_segment:
                    story_segments.append(current_segment)

                # Join all segments with proper spacing
                complete_story = ' '.join(story_segments)

                # Clean up any remaining markdown or special characters
                # First do segment-level cleaning to ensure each segment is properly processed
                cleaned_segments = []
                for segment in story_segments:
                    # Remove Scene markers and other markdown formatting
                    cleaned = segment
                    # Remove Scene markers (** or ** followed by text)
                    cleaned = re.sub(r'\*\*Scene \d+:?\*\*', '', cleaned)
                    # Remove any other bold markers but keep the text inside
                    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
                    # Remove * characters that might remain
                    cleaned = cleaned.replace('*', '')
                    # Remove any leading/trailing whitespace
                    cleaned = cleaned.strip()

                    # Ensure the segment is not empty after cleaning
                    if cleaned:
                        cleaned_segments.append(cleaned)

                # Join the cleaned segments
                complete_story = ' '.join(cleaned_segments)

                # Apply global cleaning to the complete story
                complete_story = re.sub(r'#+ ', '', complete_story)  # Remove markdown headers
                complete_story = re.sub(r'.*?[Ii]mage [Pp]rompt:.*?(\n|$)', '', complete_story)

                # Enhanced filtering for image-related text that shouldn't be in narration
                complete_story = re.sub(r'\*\*[Ii]mage:?\*\*.*?(\n|$)', '', complete_story)
                complete_story = re.sub(r'[Ii]mage:.*?(\n|$)', '', complete_story)
                complete_story = re.sub(r'!\[.*?\]\(.*?\)', '', complete_story)  # Remove image markdown
                complete_story = re.sub(r'\(Image of .*?\)', '', complete_story)  # Remove image descriptions
                complete_story = re.sub(r'Scene \d+:', '', complete_story)  # Remove any "Scene X:" text

                complete_story = re.sub(r'```.*?```', '', complete_story, flags=re.DOTALL)  # Remove code blocks
                complete_story = ' '.join(complete_story.split())  # Normalize whitespace

                print("\n--- Story Collection Complete ---")
                print(f"Collected {len(story_segments)} story segments")
                for i, segment in enumerate(story_segments):
                    print(f"Segment {i+1} preview: {segment[:50]}...")

                # Return segments if requested
                if return_segments:
                    return story_segments

                # Return empty string fallback prevention
                if not complete_story.strip():
                    print("⚠️ No story content extracted, using raw text as fallback")
                    # Create a simple cleaned version of the raw text as fallback
                    fallback_text = re.sub(r'\*\*.*?\*\*', '', raw_text)
                    fallback_text = re.sub(r'```.*?```', '', fallback_text, flags=re.DOTALL)
                    fallback_text = ' '.join(fallback_text.split())
                    return fallback_text

                return complete_story

            except Exception as e:
                print(f"⚠️ Error collecting story: {e}")
                import traceback
                traceback.print_exc()
                # Create a simple fallback for any error case
                fallback_text = re.sub(r'\*\*.*?\*\*', '', raw_text)
                fallback_text = ' '.join(fallback_text.split())
                return fallback_text  # Return cleaned original text if processing fails

        # After generating story and images, create audio
        if story_text and image_files:
            print("\n--- Starting Text-to-Speech Generation with Kokoro ---")
            try:
                # First collect and clean the complete story
                complete_story = collect_complete_story(story_text)

                # Check if we have enough segments for a complete story
                story_segments = collect_complete_story(story_text, return_segments=True)
                print(f"Story has {len(story_segments)} segments")

                # Check if we have matching image count (each segment should have one image)
                segments_count = len(story_segments)
                images_count = len(image_files)

                print(f"Story segments: {segments_count}, Images: {images_count}")

                # If we don't have enough segments or have mismatched images, try to regenerate
                retry_count = 0
                max_retries = 1000
                min_segments = 6  # Require at least 6 segments for a complete story

                # Define conditions for regeneration
                needs_regeneration = (segments_count < min_segments) or (images_count < segments_count)

                while needs_regeneration and retry_count < max_retries:
                    retry_count += 1

                    if segments_count < min_segments:
                        print(f"\n⚠️ Story has only {segments_count} segments, which is less than the required {min_segments}.")

                    if images_count < segments_count:
                        print(f"\n⚠️ Mismatch between story segments ({segments_count}) and images ({images_count}).")

                    print(f"Attempting to regenerate a more detailed story with complete images (attempt {retry_count}/{max_retries})...")

                    # Modify prompt to encourage a complete story with images for each segment
                    enhanced_prompt = prompt_text
                    if "with at least 6 detailed scenes" not in enhanced_prompt:
                        # Add more specific instructions to generate a longer story with images
                        enhanced_prompt = enhanced_prompt.replace(
                            "Generate a story about",
                            "Generate a detailed story with at least 6 scenes about"
                        )
                    if "with one image per scene" not in enhanced_prompt:
                        enhanced_prompt += " Please create one clear image for each scene in the story."

                    # Retry with the enhanced prompt
                    retry_contents = [
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=enhanced_prompt),
                            ],
                        ),
                    ]

                    # Clear previous results
                    story_text_retry = ""
                    image_files_retry = []

                    try:
                        # Try non-streaming for retries as it's more reliable
                        # Wrap the regeneration API call in the retry mechanism
                        def attempt_retry_generation():
                            return client.models.generate_content(
                                model=model,
                                contents=retry_contents,
                                config=generate_content_config,
                            )

                        retry_response = retry_api_call(attempt_retry_generation)

                        if retry_response.candidates and retry_response.candidates[0].content:
                            for part in retry_response.candidates[0].content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    inline_data = part.inline_data
                                    image_data = inline_data.data
                                    mime_type = inline_data.mime_type

                                    # Save image to a temporary file
                                    img_path = os.path.join(temp_dir, f"image_retry_{len(image_files_retry)}.jpg")
                                    with open(img_path, "wb") as f:
                                        f.write(image_data)
                                    image_files_retry.append(img_path)

                                    print(f"\n\n🖼️ --- Retry Image Received ({mime_type}) ---")
                                    display(Image(data=image_data))
                                    print("--- End Image ---\n")
                                elif hasattr(part, 'text') and part.text:
                                    print(part.text)
                                    story_text_retry += part.text

                        # Check if the retry generated enough content AND enough images
                        if story_text_retry:
                            story_segments = collect_complete_story(story_text_retry, return_segments=True)
                            segments_count = len(story_segments)
                            images_count = len(image_files_retry)

                            print(f"Retry generated {segments_count} segments and {images_count} images")

                            # Verify that we have sufficient segments AND images
                            if segments_count >= min_segments and images_count >= segments_count * 0.8:  # Allow for some missing images (80% coverage)
                                story_text = story_text_retry
                                if image_files_retry:
                                    image_files = image_files_retry
                                complete_story = collect_complete_story(story_text)
                                print("✅ Successfully regenerated a more detailed story with images")
                                needs_regeneration = False
                            else:
                                print("⚠️ Regenerated story still doesn't meet requirements")

                                # If we have good segment count but poor image count, keep trying
                                if segments_count >= min_segments and images_count < segments_count * 0.8:
                                    print("Generated enough segments but not enough images. Retrying...")
                                    # We'll continue the loop to try again
                    except Exception as retry_error:
                        print(f"⚠️ Error during story regeneration: {retry_error}")

                print("⏳ Converting complete story to speech...")
                print("Story to be converted:", complete_story[:100] + "...")

                # Initialize Kokoro pipeline
                pipeline = KPipeline(lang_code='a')

                try:
                    # Generate audio for the complete story
                    print("Full story length:", len(complete_story), "characters")
                    generator = pipeline(complete_story, voice='af_heart')

                    # Save the complete audio file
                    audio_path = os.path.join(temp_dir, "complete_story.wav")

                    # Process and save all audio chunks
                    all_audio = []
                    for _, (gs, ps, audio) in enumerate(generator):
                        all_audio.append(audio)

                    # Combine all audio chunks
                    if all_audio:
                        combined_audio = np.concatenate(all_audio)
                        sf.write(audio_path, combined_audio, 24000)
                        print(f"✅ Complete story audio saved to: {audio_path}")
                        print("🔊 Playing complete story audio:")
                        display(Audio(data=combined_audio, rate=24000))

                except Exception as e:
                    print(f"⚠️ Error in text-to-speech generation: {e}")
                    return

                bark_audio_success = False

            except Exception as e:
                print(f"⚠️ Error in text-to-speech generation: {e}")
                return

            # Create video from images and audio
            print("\n--- Creating Video from Images and Audio ---")
            print("⏳ Creating video...")

            # Prepare images for FFMPEG
            # First, ensure all images are the same size (1920x1080) for YouTube HD quality
            # Then we'll downscale to 1280x720 for the final thumbnail with better quality
            resized_images = []
            for idx, img_path in enumerate(image_files):
                img = PILImage.open(img_path)
                # Use high-quality resizing with antialiasing for best quality
                resized_img = img.resize((1920, 1080), PILImage.LANCZOS)
                resized_path = os.path.join(temp_dir, f"resized_{idx}.jpg")
                # Save with high quality (95%)
                resized_img.save(resized_path, quality=95, optimize=True)
                resized_images.append(resized_path)

            # Create a text file listing all images for FFMPEG
            image_list_path = os.path.join(temp_dir, "image_list.txt")

            # Calculate approximate duration based on audio file
            try:
                # Use ffprobe to get audio duration if ffmpeg is available
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                audio_duration = float(result.stdout.strip())
            except Exception:
                # Fallback duration estimation
                if 'bark_audio_success' in locals() and bark_audio_success:
                    audio_duration = len(combined_audio) / SAMPLE_RATE
                else:
                    # gTTS fallback
                    word_count = len(story_text.split())
                    audio_duration = word_count * 0.5  # rough estimate

            # Calculate duration for each image
            if len(resized_images) > 0:
                image_duration = audio_duration / len(resized_images)

                # Create the image list file with durations
                with open(image_list_path, 'w') as f:
                    for img_path in resized_images:
                        f.write(f"file '{img_path}'\n")
                        f.write(f"duration {image_duration}\n")
                    # Write the last image path again (required by FFMPEG)
                    f.write(f"file '{resized_images[-1]}'\n")

                # Output video path
                output_path = os.path.join(temp_dir, "story_video.mp4")

                # Use advanced FFMPEG command with Frei0r effects
                print("⏳ Running FFmpeg with Frei0r effects for enhanced storytelling...")
                try:
                    # Create complex filter string for each image with effects
                    filter_complex = []

                    # Import random for selecting effects randomly
                    import random

                    # Define simple motion effects for storytelling enhancement
                    # Each effect is designed to work well with static images
                    motion_effects = [
                        # 1. Zoom In effect - slowly enlarges the image (Ken Burns effect)
                        lambda i: f"[v{i}]zoompan=z='min(zoom+0.0015,1.4)':d={int(image_duration*25)}:s=1920x1080[v{i}e];",

                        # 2. Pan Left/Right - moves horizontally across the image
                        lambda i: f"[v{i}]zoompan=z=1.2:x='iw/2-(iw/zoom/2)+((iw/zoom/2)/100)*n':d={int(image_duration*25)}:s=1920x1080[v{i}e];",

                        # 3. Pan Up/Down - moves vertically across the image
                        lambda i: f"[v{i}]zoompan=z=1.2:y='ih/2-(ih/zoom/2)+sin(n/120)*100':d={int(image_duration*25)}:s=1920x1080[v{i}e];",

                        # 4. Shake/Jitter - adds micro-movements for handheld camera feel
                        lambda i: f"[v{i}]zoompan=z=1.01:x='iw/2-(iw/zoom/2)+sin(n*5)*10':y='ih/2-(ih/zoom/2)+cos(n*5)*10':d={int(image_duration*25)}:s=1920x1080[v{i}e];",

                        # 5. Tilt - slight angular rotation
                        lambda i: f"[v{i}]rotate='0.02*sin(n/30)':fillcolor=black:c=bilinear:s=1920x1080[v{i}e];",

                        # 8. Rotate - subtle rotation to mimic dynamic camera
                        lambda i: f"[v{i}]rotate='0.01*sin(n/40)':fillcolor=black:c=bilinear:s=1920x1080[v{i}e];",

                        # 9. Scale Bounce - light zoom in/out bounce loop
                        lambda i: f"[v{i}]zoompan=z='1.05+0.05*sin(n/25)':d={int(image_duration*25)}:s=1920x1080[v{i}e];",

                        # 14. Color Pulse - subtle brightness shifts
                        lambda i: f"[v{i}]curves=all='0/0 0.5/0.55 1/1'[v{i}e];",

                        # 15. Zoom with Rotation - slight zoom while spinning slowly
                        lambda i: f"[v{i}]zoompan=z='min(zoom+0.001,1.2)':d={int(image_duration*25)}:s=1920x1080,rotate='0.008*n':fillcolor=black:c=bilinear[v{i}e];",
                    ]

                    # Define transition effects for connecting scenes
                    transition_effects = [
                        # 6. Fade In/Out - smooth transition
                        lambda i, duration: f"[v{i}e]fade=t=in:st=0:d=0.7,fade=t=out:st={duration-0.7}:d=0.7[f{i}];",

                        # 7. Slide In/Out - moves from a direction
                        lambda i, duration: f"[v{i}e]fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.6}:d=0.6[f{i}];",

                        # 12. Blur In/Out - start blurred, sharpen over time
                        lambda i, duration: f"[v{i}e]boxblur=10:enable='lt(t,0.8)':t=max(0,1-t/{0.8})',fade=t=in:st=0:d=0.3,fade=t=out:st={duration-0.5}:d=0.5[f{i}];",

                        # 13. Glitch Effect - quick jitter & distortion
                        lambda i, duration: f"[v{i}e]hue='n*2':enable='if(lt(mod(t,1),0.1),1,0)',fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.6}:d=0.6[f{i}];",
                    ]

                    # Create combined effects pool
                    all_effects = motion_effects

                    for i in range(len(resized_images)):
                        # Add scale filter to ensure consistent size
                        filter_complex.append(f"[{i}:v]scale=1920:1080,setsar=1[v{i}];")

                        # Randomly select effects based on image count
                        # If we have N images, each image gets one of N randomly selected effects
                        total_images = len(resized_images)

                        # Calculate number of effects to use - equal to number of images
                        num_effects_to_use = min(total_images, len(all_effects))

                        # Create a deterministic but varied effect selection based on image position
                        # This ensures each image gets a different effect while maintaining consistency
                        # across multiple runs with the same number of images
                        random.seed(i + 42)  # Seed based on image position for deterministic variation
                        effect_index = i % len(all_effects)  # Cycle through effects based on image position

                        # Apply the selected effect - still maintains story flow with varied effects
                        filter_complex.append(all_effects[effect_index](i))
                        random.seed()  # Reset seed for other random selections

                    # Apply transitions with storytelling intent - keep this part of the story-driven approach
                    for i in range(len(resized_images)):
                        # Transition selection based on story position
                        story_position = i / len(resized_images)

                        if i == 0:
                            # First image just needs fade in
                            filter_complex.append(f"[v{i}e]fade=t=in:st=0:d=0.5[f{i}];")
                        else:
                            # Select transition based on story position
                            if story_position < 0.3:
                                transition_index = 0  # Fade for beginning
                            elif story_position < 0.7:
                                transition_index = 1  # Slide for middle
                            elif story_position < 0.9:
                                transition_index = 2  # Blur for climax
                            else:
                                transition_index = 3  # Glitch for resolution/finale

                            # Apply the selected transition
                            filter_complex.append(transition_effects[transition_index % len(transition_effects)](i, image_duration))

                    # Create concatenation string
                    concat_str = ""
                    for i in range(len(resized_images)):
                        concat_str += f"[f{i}]"
                    concat_str += f"concat=n={len(resized_images)}:v=1:a=0[outv]"
                    filter_complex.append(concat_str)

                    # Join all filters
                    filter_complex_str = ''.join(filter_complex)

                    # Build input files list
                    input_files = []
                    for img in resized_images:
                        input_files.extend(['-loop', '1', '-t', str(image_duration), '-i', img])

                    # Create complete FFmpeg command with Frei0r
                    cmd = [
                        'ffmpeg', '-y',
                    ] + input_files + [
                        '-i', audio_path,
                        '-filter_complex', filter_complex_str,
                        '-map', '[outv]',
                        '-map', '1:a',
                        '-c:v', 'libx264',
                        '-preset', 'slow',  # Better quality encoding
                        '-crf', '18',       # High quality (lower is better, 18-23 is good range)
                        '-c:a', 'aac',
                        '-b:a', '192k',     # Higher audio bitrate
                        '-pix_fmt', 'yuv420p',
                        '-shortest',
                        '-r', '30',         # Increased framerate for smoother motion
                        output_path
                    ]

                    # Run the enhanced command
                    try:
                        result = subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=True
                        )
                        print("✅ Enhanced video with effects created successfully!")
                    except subprocess.CalledProcessError as e:
                        # If enhanced command fails, try the fallback
                        print("⚠️ Enhanced video creation failed, trying fallback method...")
                        print(f"Error: {e.stderr.decode() if hasattr(e.stderr, 'decode') else str(e)}")
                        result = subprocess.run(
                            [
                                'ffmpeg', '-y',
                                '-f', 'concat',
                                '-safe', '0',
                                '-i', image_list_path,
                                '-i', audio_path,
                                '-c:v', 'libx264',
                                '-c:a', 'aac',
                                '-pix_fmt', 'yuv420p',
                                '-shortest',
                                output_path
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=True
                        )
                        print("✅ Video created successfully with basic method")

                    print(f"✅ Video created at: {output_path}")
                    # Display the video
                    print("🎬 Playing the created video:")
                    display(HTML(f"""
                    <video width="640" height="360" controls>
                        <source src="file://{output_path}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    """))

                    # Save video to Google Drive using the API rather than mounting
                    # The API-based saving functionality is implemented below outside of this function
                    print("\n--- Video will be saved to Google Drive using API ---")
                    print("💡 Check the output below for Google Drive upload status")

                    # Add option to download directly in the notebook
                    try:
                        print("\n--- Download Video ---")
                        # Get file size in MB
                        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)

                        if file_size_mb < 50:  # Only try data URL method for files under 50MB
                            with open(output_path, "rb") as video_file:
                                video_data = video_file.read()
                                b64_data = base64.b64encode(video_data).decode()
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                display(HTML(f"""
                                <a href="data:video/mp4;base64,{b64_data}"
                                   download="gemini_story_{timestamp}.mp4"
                                   style="
                                       display: inline-block;
                                       padding: 10px 20px;
                                       background-color: #4CAF50;
                                       color: white;
                                       text-decoration: none;
                                       border-radius: 5px;
                                       font-weight: bold;
                                       margin-top: 10px;
                                   ">
                                   Download Video ({file_size_mb:.1f} MB)
                                </a>
                                """))
                        else:
                            print("⚠️ Video file is too large for direct download in notebook.")
                            print(f"Video size: {file_size_mb:.1f} MB")
                            print("Please download it from the location shown above.")
                    except Exception as e:
                        print(f"⚠️ Could not create download button: {e}")
                        print("Please download the video from the path shown above.")

                except subprocess.CalledProcessError as e:
                    print(f"🛑 Error creating video: {e}")
                    print(f"FFmpeg stderr: {e.stderr.decode()}")

                    # If FFmpeg is not installed or fails, just display the images
                    print("\n⚠️ Video creation failed. Displaying images instead:")
                    for img_path in resized_images:
                        display(Image(filename=img_path))
            else:
                print("⚠️ No images available for video creation.")

    except Exception as e:
        print(f"\n🛑 An error occurred during streaming or processing: {e}")
        import traceback
        traceback.print_exc()

    # --- Google Drive API Integration ---
    if output_path and os.path.exists(output_path):
        try:
            print("\n--- Saving Video to Google Drive using API ---")

            # Import necessary libraries for Google Drive API
            try:
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
                from google.oauth2 import service_account
                import io
                import json

                # Download and use credentials from Google Drive link instead of hardcoding them
                credentials_file_id = "152LtocR_Lvll37IW3GXJWAowLS02YBF2"
                credentials_file_path = os.path.join(temp_dir, "drive_credentials.json")
                
                print("⏳ Downloading Google Drive API credentials from the provided link...")
                try:
                    # Function to download file by ID from Google Drive without authentication
                    def download_file_from_google_drive(file_id, destination):
                        import requests
                        
                        # Create the direct download URL
                        url = f"https://drive.google.com/uc?id={file_id}&export=download"
                        
                        # Make the initial request to get the download link
                        session = requests.Session()
                        response = session.get(url, stream=True)
                        
                        # Handle potential confirmation page (for large files)
                        for key, value in response.cookies.items():
                            if key.startswith('download_warning'):
                                url = f"{url}&confirm={value}"
                                response = session.get(url, stream=True)
                        
                        # Save the file
                        with open(destination, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=32768):
                                if chunk:
                                    f.write(chunk)
                        
                        return destination
                    
                    # Download the credentials file
                    download_file_from_google_drive(credentials_file_id, credentials_file_path)
                    print(f"✅ Credentials file downloaded to: {credentials_file_path}")
                    
                    # Set up credentials from the downloaded file
                    credentials = service_account.Credentials.from_service_account_file(
                        credentials_file_path,
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                    print("✅ Successfully loaded credentials from downloaded file")
                    
                except Exception as e:
                    print(f"⚠️ Error downloading or loading credentials: {e}")
                    print("Attempting to continue with alternative methods...")
                    raise

                drive_service = build('drive', 'v3', credentials=credentials)

                # Create main folder if it doesn't exist
                main_folder_name = 'GeminiStories'
                main_folder_id = None

                # Check if main folder exists
                query = f"name='{main_folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                results = drive_service.files().list(q=query).execute()
                items = results.get('files', [])

                if not items:
                    # Create main folder
                    print(f"Creating main folder '{main_folder_name}'...")
                    folder_metadata = {
                        'name': main_folder_name,
                        'mimeType': 'application/vnd.google-apps.folder'
                    }
                    main_folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
                    main_folder_id = main_folder.get('id')
                else:
                    main_folder_id = items[0]['id']

                print(f"✅ Using main folder: {main_folder_name} (ID: {main_folder_id})")

                # Generate a timestamp for the folder name
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                story_folder_name = f"{timestamp}_story"

                # Create a folder for this story
                story_folder_metadata = {
                    'name': story_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [main_folder_id]
                }

                story_folder = drive_service.files().create(body=story_folder_metadata, fields='id').execute()
                story_folder_id = story_folder.get('id')
                print(f"✅ Created story folder: {story_folder_name} (ID: {story_folder_id})")

                # Generate SEO metadata if needed
                if 'metadata' not in locals() or not metadata:
                    metadata = generate_seo_metadata(story_text, image_files, prompt_text)

                # Generate thumbnail if needed
                if 'thumbnail_path' not in locals() or not thumbnail_path:
                    thumbnail_path = generate_thumbnail(image_files, story_text, metadata)

                # Upload video
                print("⏳ Uploading video to Google Drive...")
                video_metadata = {
                    'name': 'video.mp4',
                    'parents': [story_folder_id]
                }

                media = MediaFileUpload(output_path, mimetype='video/mp4', resumable=True)
                video_file = drive_service.files().create(
                    body=video_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                print(f"✅ Video uploaded successfully (File ID: {video_file.get('id')})")

                # Helper function to upload text files to Google Drive
                def upload_text_file_to_drive(content, filename, parent_folder_id):
                    """Upload a text file to Google Drive using a temporary file approach.
                    
                    Args:
                        content: The text content to upload
                        filename: The name of the file in Google Drive
                        parent_folder_id: The ID of the parent folder
                        
                    Returns:
                        The file ID of the uploaded file
                    """
                    # Create file metadata
                    file_metadata = {
                        'name': filename,
                        'parents': [parent_folder_id]
                    }
                    
                    # Create a temporary file
                    temp_file_path = os.path.join(temp_dir, filename)
                    with open(temp_file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # Upload the file directly
                    file_media = MediaFileUpload(temp_file_path, mimetype='text/plain', resumable=False)
                    file = drive_service.files().create(
                        body=file_metadata,
                        media_body=file_media,
                        fields='id'
                    ).execute()
                    
                    return file.get('id')
                
                # Upload metadata files
                # Title
                title_content = metadata['title']
                title_file_id = upload_text_file_to_drive(title_content, 'title.txt', story_folder_id)

                # Description
                desc_content = metadata['description']
                desc_file_id = upload_text_file_to_drive(desc_content, 'description.txt', story_folder_id)

                # Tags
                tags_content = '\n'.join(metadata['tags'])
                tags_file_id = upload_text_file_to_drive(tags_content, 'tags.txt', story_folder_id)

                # Upload thumbnail if available
                if thumbnail_path and os.path.exists(thumbnail_path):
                    thumb_metadata = {
                        'name': 'thumbnail.jpg',
                        'parents': [story_folder_id]
                    }

                    thumb_media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg', resumable=True)
                    thumb_file = drive_service.files().create(
                        body=thumb_metadata,
                        media_body=thumb_media,
                        fields='id'
                    ).execute()

                    print(f"✅ Thumbnail uploaded successfully (File ID: {thumb_file.get('id')})")

                # Get a direct link to the folder
                folder_link = f"https://drive.google.com/drive/folders/{story_folder_id}"
                print(f"\n✅ All files uploaded successfully to Google Drive!")
                print(f"📁 Folder link: {folder_link}")

                # Display a summary of the uploaded content
                print("\n--- Upload Summary ---")
                print(f"• Video: video.mp4")
                print(f"• Title: {metadata['title']}")
                print(f"• Description: {len(metadata['description'])} characters")
                print(f"• Tags: {len(metadata['tags'])} tags")
                if thumbnail_path and os.path.exists(thumbnail_path):
                    print(f"• Thumbnail: thumbnail.jpg")
                    
                # Important: Completely stop execution after successful upload
                print("\n✅✅✅ Upload to Google Drive successful! Script execution will stop now to prevent unnecessary retries.")
                print("🛑 Terminating script execution...")
                
                # Force exit the script with success code
                import sys
                sys.exit(0)

            except ImportError as ie:
                print(f"⚠️ Required libraries for Google Drive API not installed: {ie}")
                print("💡 To use Google Drive API, install these packages:")
                print("   pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2")
                print("\n💡 You can manually download the video from the temporary location:")
                print(f"   {output_path}")

        except Exception as e:
            print(f"⚠️ Error uploading to Google Drive: {e}")
            print("💡 You can manually download the video from the temporary location:")
            print(f"   {output_path}")

    # --- Direct Download Option ---
    # Skip this section if we already uploaded to Google Drive
    # This section is only for when Google Drive upload was not available or failed
    if 'drive_service' not in locals() and output_path and os.path.exists(output_path):
        print("\n--- Download Video ---")
        # Get file size in MB
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)

        if file_size_mb < 50:  # Only try data URL method for files under 50MB
            with open(output_path, "rb") as video_file:
                video_data = video_file.read()
                b64_data = base64.b64encode(video_data).decode()
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                display(HTML(f"""
                <a href="data:video/mp4;base64,{b64_data}"
                   download="gemini_story_{timestamp}.mp4"
                   style="
                       display: inline-block;
                       padding: 10px 20px;
                       background-color: #4CAF50;
                       color: white;
                       text-decoration: none;
                       border-radius: 5px;
                       font-weight: bold;
                       margin-top: 10px;
                   ">
                   Download Video ({file_size_mb:.1f} MB)
                </a>
                """))
        else:
            print("⚠️ Video file is too large for direct download in notebook.")
            print(f"Video size: {file_size_mb:.1f} MB")
            print("Please download it from the location shown above.")
        try:
            print("⚠️ Video file is too large for direct download in notebook.")
            print(f"Video size: {file_size_mb:.1f} MB")
            print("Please download it from the location shown above.")
        except Exception as e:
            print(f"⚠️ Could not create download button: {e}")
            print("Please download the video from the path shown above.")

# Function to generate SEO-friendly title, description, and tags
def generate_seo_metadata(story_text, image_files, prompt_text):
    """
    Generates SEO-friendly title, description, and tags for the video.

    Args:
        story_text: The complete story text
        image_files: List of images from the story
        prompt_text: The original prompt used to generate the story

    Returns:
        Dictionary containing title, description, and tags
    """
    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        print("✅ Initializing SEO metadata generator client...")
    except Exception as e:
        print(f"🔴 Error initializing SEO metadata generator client: {e}")
        return default_seo_metadata(story_text, prompt_text)

    # Use the same model as prompt generation for metadata
    model = "gemini-2.0-flash-thinking-exp-01-21"

    # Extract the first 1000 characters to give the model a sense of the story
    story_preview = story_text[:1000] + "..." if len(story_text) > 1000 else story_text

    # Create prompt for SEO metadata generation
    seo_prompt = f"""
    I need to create SEO-friendly metadata for a children's story video.

    Here is a preview of the story:
    ```
    {story_preview}
    ```

    Original prompt that generated this story:
    ```
    {prompt_text}
    ```

    Please generate the following in JSON format:
    1. A catchy YouTube-style title (max 60 characters) that will attract families with children
    2. An engaging description (150-300 words) that describes the story, mentions key moments, and includes relevant keywords
    3. A list of 10-15 tags relevant to the content (children's stories, animation, etc.)

    Format your response ONLY as a valid JSON object with keys: "title", "description", and "tags" (as an array).
    """

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=seo_prompt),
            ],
        ),
    ]

    print("⏳ Generating SEO-friendly metadata...")

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
        )

        if response.candidates and response.candidates[0].content:
            response_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    response_text += part.text

            # Extract the JSON data from the response
            # First, try to find JSON within markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                # If no markdown code blocks, try to extract the entire response
                json_str = response_text

            # Parse the JSON data
            try:
                metadata = json.loads(json_str)
                # Validate the metadata
                if not all(key in metadata for key in ['title', 'description', 'tags']):
                    print("⚠️ Metadata is missing required fields, using fallback...")
                    return default_seo_metadata(story_text, prompt_text)

                print("✅ SEO metadata generated successfully")
                return metadata
            except json.JSONDecodeError:
                print("⚠️ Failed to parse metadata as JSON, using fallback...")
                return default_seo_metadata(story_text, prompt_text)
    except Exception as e:
        print(f"⚠️ Error generating SEO metadata: {e}")
        return default_seo_metadata(story_text, prompt_text)

def default_seo_metadata(story_text, prompt_text):
    """
    Creates default SEO metadata if the AI generation fails.

    Args:
        story_text: The complete story text
        prompt_text: The original prompt used to generate the story

    Returns:
        Dictionary with default title, description, and tags
    """
    # Extract character and setting from the prompt if possible
    import re
    char_setting = re.search(r'about\s+(.*?)\s+going\s+on\s+an\s+adventure\s+in\s+(.*?)(?:\s+in\s+a\s+3d|\.)',
                             prompt_text)

    character = "an animal"
    setting = "an adventure"

    if char_setting:
        character = char_setting.group(1)
        setting = char_setting.group(2)

    # Create a timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")

    # Create default metadata
    title = f"Adventure of {character} in {setting} | Children's Story"
    title = title[:60]  # Ensure title is not too long

    # Create a brief description from the beginning of the story
    story_preview = story_text[:500] + "..." if len(story_text) > 500 else story_text
    description = f"""
    Join {character} on an exciting adventure in {setting}!

    {story_preview}

    This animated children's story is perfect for bedtime reading, family story time, or whenever your child wants to explore magical worlds and learn valuable lessons. Watch as our character overcomes challenges and discovers new friends along the way.

    #ChildrensStory #Animation #KidsEntertainment

    Created: {timestamp}
    """

    # Default tags
    tags = [
        "children's story",
        "kids animation",
        "bedtime story",
        "animated story",
        character,
        setting,
        "family friendly",
        "kids entertainment",
        "story time",
        "animated adventure",
        "educational content",
        "preschool",
        "moral story",
        "3D animation",
        "storybook"
    ]

    print("✅ Created default SEO metadata")
    return {
        "title": title,
        "description": description,
        "tags": tags
    }

def generate_thumbnail(image_files, story_text, metadata):
    """
    Generates a video thumbnail using one of the generated images and adding text overlay.

    Args:
        image_files: List of images from the story
        story_text: The complete story text
        metadata: The SEO metadata dictionary

    Returns:
        Path to the generated thumbnail
    """
    print("⏳ Generating video thumbnail...")

    try:
        # Select the best image for thumbnail
        # Typically one of the first few images works well as they introduce the character
        if not image_files:
            print("⚠️ No images available for thumbnail generation")
            return None

        # Choose image based on availability - prioritize 2nd image if available (often shows main character clearly)
        thumbnail_base_img = image_files[min(1, len(image_files) - 1)]

        # Create a temporary file for the thumbnail
        thumbnail_path = os.path.join(os.path.dirname(thumbnail_base_img), "thumbnail.jpg")

        # Open the image using PIL
        from PIL import Image, ImageDraw, ImageFont

        # Open and resize the image to standard YouTube thumbnail size (1920x1080) for high quality
        # Then we'll downscale to 1280x720 for the final thumbnail with better quality
        img = Image.open(thumbnail_base_img)
        # First upscale if needed to ensure we have enough details
        if img.width < 1920 or img.height < 1080:
            img = img.resize((1920, 1080), PILImage.LANCZOS)

        # Ensure proper aspect ratio for YouTube thumbnail
        img = img.resize((1280, 720), PILImage.LANCZOS)

        # Create a drawing context
        draw = ImageDraw.Draw(img)

        # Try to load a font, with fallback to default
        try:
            # Try to find a suitable font
            font_path = None

            # List of common system fonts to try
            font_names = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
                '/System/Library/Fonts/Supplemental/Arial Bold.ttf',     # macOS
                'C:\\Windows\\Fonts\\arialbd.ttf',                       # Windows
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',  # Another Linux option
            ]

            for font_name in font_names:
                if os.path.exists(font_name):
                    font_path = font_name
                    break

            # Use the font if found, otherwise will use default
            if font_path:
                # Title font (large)
                title_font = ImageFont.truetype(font_path, 60)
                # Get the title from metadata
                title = metadata['title']

                # Measure text size to position it
                text_width = draw.textlength(title, font=title_font)

                # Add semi-transparent background for better readability
                # Draw a rectangle at the bottom for the title
                rectangle_height = 120
                draw.rectangle(
                    [(0, img.height - rectangle_height), (img.width, img.height)],
                    fill=(0, 0, 0, 180)  # Semi-transparent black
                )

                # Draw the title text
                draw.text(
                    (img.width / 2 - text_width / 2, img.height - rectangle_height / 2 - 30),
                    title,
                    font=title_font,
                    fill=(255, 255, 255)  # White color
                )

                # Add a small banner at the top for "Children's Story"
                draw.rectangle(
                    [(0, 0), (img.width, 80)],
                    fill=(0, 0, 0, 150)  # Semi-transparent black
                )

                # Use a smaller font for the banner
                banner_font = ImageFont.truetype(font_path, 40)
                banner_text = "Children's Story Animation"
                banner_width = draw.textlength(banner_text, font=banner_font)

                draw.text(
                    (img.width / 2 - banner_width / 2, 20),
                    banner_text,
                    font=banner_font,
                    fill=(255, 255, 255)  # White color
                )
            else:
                print("⚠️ Could not find a suitable font, using basic text overlay")
                # Use PIL's default font
                # Add semi-transparent black rectangles for text placement
                draw.rectangle(
                    [(0, img.height - 100), (img.width, img.height)],
                    fill=(0, 0, 0, 180)
                )
                draw.rectangle(
                    [(0, 0), (img.width, 80)],
                    fill=(0, 0, 0, 150)
                )

                # Add text - simplified when no font is available
                draw.text(
                    (40, img.height - 80),
                    metadata['title'][:50],
                    fill=(255, 255, 255)
                )
                draw.text(
                    (40, 30),
                    "Children's Story Animation",
                    fill=(255, 255, 255)
                )

        except Exception as font_error:
            print(f"⚠️ Error with font rendering: {font_error}")
            # Add basic text using default settings
            draw.rectangle(
                [(0, img.height - 100), (img.width, img.height)],
                fill=(0, 0, 0, 180)
            )
            draw.text(
                (40, img.height - 80),
                metadata['title'][:50],
                fill=(255, 255, 255)
            )

        # Save the thumbnail
        img.save(thumbnail_path, quality=95)
        print(f"✅ Thumbnail generated and saved to: {thumbnail_path}")

        return thumbnail_path

    except Exception as e:
        print(f"⚠️ Error generating thumbnail: {e}")
        return None

# --- Run the function ---
print("--- Starting generation (attempting 16:9 via prompt) ---")
# You can set use_prompt_generator=True to enable the prompt generator model
# You can also customize the prompt_input to guide the prompt generator
retry_story_generation(use_prompt_generator=True)
print("--- Generation function finished ---")