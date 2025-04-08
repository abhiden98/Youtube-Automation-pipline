import os
import re
import json
import tempfile
import numpy as np
import soundfile as sf
import subprocess
import base64
import datetime
from google import genai
from google.genai import types
from IPython.display import display, Image, Audio, HTML
from PIL import Image as PILImage

from src.generators.prompt_generation import generate_prompt
from src.utils.api_utils import retry_api_call, get_safety_settings
from src.generators.metadata_generator import generate_seo_metadata, default_seo_metadata, generate_thumbnail
from src.utils.google_drive_utils import download_file_from_google_drive, upload_text_file_to_drive

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
        safety_settings=get_safety_settings(),
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

        # After generating story and images, create audio
        if story_text and image_files:
            print("\n--- Starting Text-to-Speech Generation with Kokoro ---")
            try:
                # First collect and clean the complete story
                from src.generators.story_generator import retry_story_generation, collect_complete_story
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
                from kokoro import KPipeline
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
            from src.generators.video_generator import create_video
            output_path = create_video(image_files, audio_path, temp_dir)
            
            # Generate SEO metadata if needed
            if 'metadata' not in locals() or not metadata:
                metadata = generate_seo_metadata(story_text, image_files, prompt_text)
            
            # Generate thumbnail if needed
            if 'thumbnail_path' not in locals() or not thumbnail_path:
                thumbnail_path = generate_thumbnail(image_files, story_text, metadata)

            # --- Google Drive API Integration ---
            if output_path and os.path.exists(output_path):
                from src.services.google_drive_upload import upload_to_google_drive
                upload_to_google_drive(output_path, story_text, image_files, metadata, thumbnail_path, temp_dir)

    except Exception as e:
        print(f"\n🛑 An error occurred during streaming or processing: {e}")
        import traceback
        traceback.print_exc()
        
    return {
        "story_text": story_text if 'story_text' in locals() else None,
        "image_files": image_files if 'image_files' in locals() else [],
        "output_path": output_path if 'output_path' in locals() else None,
        "thumbnail_path": thumbnail_path if 'thumbnail_path' in locals() else None,
        "metadata": metadata if 'metadata' in locals() else None
    }
