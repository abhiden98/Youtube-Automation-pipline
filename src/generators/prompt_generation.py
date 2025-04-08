import os
import re
from google import genai
from google.genai import types

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
