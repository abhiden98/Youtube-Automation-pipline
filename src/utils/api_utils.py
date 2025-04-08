import time
import json
from google.genai import types

def retry_api_call(retry_function, *args, **kwargs):
    """
    Retries API calls when the Gemini model server is unavailable or encounters errors.

    Args:
        retry_function: The function to retry (either generate_prompt or the model API call)
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of the successful function call, or None after maximum retries
    """
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

def get_safety_settings():
    """Return the standard safety settings for the Gemini model."""
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]
    return safety_settings
