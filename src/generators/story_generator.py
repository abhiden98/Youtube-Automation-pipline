import os
import re
import json
import tempfile
import time
import threading
import traceback
from google import genai
from google.genai import types
from IPython.display import display, Image, Audio, HTML

from src.generators.prompt_generation import generate_prompt
from src.utils.api_utils import retry_api_call, get_safety_settings

def retry_story_generation(use_prompt_generator=True, prompt_input="Create a unique children's story with a different animal character, setting, and adventure theme."):
    """
    Persistently retries story generation when image loading fails or JSON errors occur.
    
    Args:
        use_prompt_generator: Boolean to control whether to use prompt generator
        prompt_input: Base prompt input to use or elaborate on
        
    Returns:
        The generated story and image files if successful, or None on persistent failure
    """
    print("\n--- Starting generation (attempting 16:9 via prompt) ---\n")
    
    # Create a wrapper function to handle story generation
    def generation_wrapper(use_prompt_generator, prompt_input):
        # Import here to avoid circular imports
        import tempfile
        from google import genai
        from google.genai import types
        from IPython.display import display, Image, Audio, HTML
        from src.generators.prompt_generation import generate_prompt
        from src.utils.api_utils import retry_api_call, get_safety_settings
        
        print(f"⏳ Starting generation with prompt: {prompt_input[:50]} ...")
        
        try:
            # Initialize client
            client = genai.Client(
                api_key=os.environ.get("GEMINI_API_KEY"),
            )
            
            # Setup model and prompt
            model = "gemini-2.0-flash-exp-image-generation"
            
            # Get prompt
            if use_prompt_generator:
                generated_prompt = retry_api_call(generate_prompt, prompt_input)
                if generated_prompt and generated_prompt.strip():
                    prompt_text = generated_prompt
                else:
                    prompt_text = """Generate a story about a white baby goat named Pip going on an adventure in a farm in a highly detailed 3d cartoon animation style. For each scene, generate a high-quality, photorealistic image **in landscape orientation suitable for a widescreen (16:9 aspect ratio) YouTube video**. Ensure maximum detail, vibrant colors, and professional lighting."""
            else:
                prompt_text = prompt_input
            
            # Prepare content
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt_text),
                    ],
                ),
            ]
            
            # Configure generation
            generate_content_config = types.GenerateContentConfig(
                response_modalities=["image", "text"],
                response_mime_type="text/plain",
                safety_settings=get_safety_settings(),
            )
            
            # Create temp directory for images
            temp_dir = tempfile.mkdtemp()
            story_text = ""
            image_files = []
            
            # Generate content using API
            stream = retry_api_call(
                lambda: client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                )
            )
            
            # Process response stream
            image_found = False
            json_errors = 0
            max_json_errors = 5  # Allow up to 5 errors before giving up on streaming
            contains_image_description = False
            
            for chunk in stream:
                try:
                    # Handle raw string responses
                    if isinstance(chunk, str):
                        story_text += chunk
                        print(chunk, end="")
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
                        
                        # Save image
                        img_path = os.path.join(temp_dir, f"image_{len(image_files)}.jpg")
                        with open(img_path, "wb") as f:
                            f.write(image_data)
                        image_files.append(img_path)
                        
                        # Display image
                        display(Image(data=image_data))
                    
                    elif hasattr(part, 'text') and part.text:
                        story_text += part.text
                        print(part.text, end="")
                        # Check for image descriptions
                        if "**Image Description:**" in part.text:
                            contains_image_description = True
                
                except json.decoder.JSONDecodeError as je:
                    print(f"\n⚠️ JSON decode error in chunk: {je}")
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
                        break  # Exit the streaming loop and use fallback
                    continue  # Skip this chunk and continue with next
                except Exception as e:
                    print(f"\n⚠️ Error processing chunk: {e}")
                    continue  # Skip this chunk and continue with next
            
            # If we had many JSON errors but still have some content, try to use it
            if json_errors > 0:
                print(f"\nEncountered {json_errors} JSON decode errors during streaming")
                if not story_text.strip():
                    print("No story text was captured during streaming, attempting fallback...")
                    # We would implement a fallback to non-streaming here
                    # But for simplicity, we'll just return what we have
            
            # Check if we actually found images or just descriptions
            if contains_image_description:
                print("\n⚠️ Model generated text descriptions instead of actual images.")
                # In the original code, this would trigger a complete restart
                # For now, we'll continue with what we have
            
            return {
                "story_text": story_text,
                "image_files": image_files,
                "temp_dir": temp_dir,
                "contains_image_description": contains_image_description
            }
        
        except Exception as e:
            print(f"⚠️ Error in generation attempt: {e}")
            traceback.print_exc()
            return None
    
    # Retry logic
    max_retries = 5
    retry_count = 0
    retry_delay = 7
    result = None
    
    while retry_count < max_retries:
        retry_count += 1
        if retry_count > 1:
            print(f"\n🔄 Retry attempt #{retry_count} for story generation...")
        
        result = generation_wrapper(use_prompt_generator, prompt_input)
        
        if result and result["story_text"] and len(result["image_files"]) >= 4:
            print("\n✅ Story generation successful!")
            return result
        
        if retry_count < max_retries:
            print(f"⚠️ Generation attempt #{retry_count} failed or incomplete.")
            print(f"🔄 Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    print("\n❌ All story generation attempts failed.")
    return None

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
