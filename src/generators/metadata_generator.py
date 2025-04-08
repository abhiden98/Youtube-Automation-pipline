import os
import re
import json
import datetime
from google import genai
from google.genai import types
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

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

        # Open and resize the image to standard YouTube thumbnail size (1920x1080) for high quality
        # Then we'll downscale to 1280x720 for the final thumbnail with better quality
        img = PILImage.open(thumbnail_base_img)
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
