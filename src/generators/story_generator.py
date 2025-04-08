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
