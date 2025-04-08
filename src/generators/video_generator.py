import os
import subprocess
import random
from PIL import Image as PILImage

def create_video(image_files, audio_path, temp_dir):
    """
    Creates a video from a list of images and an audio file.
    
    Args:
        image_files: List of image file paths
        audio_path: Path to the audio file
        temp_dir: Temporary directory to store intermediate files
        
    Returns:
        Path to the created video file
    """
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
            with open(audio_path, 'rb') as f:
                # Read the audio file to get duration estimate
                audio_data = f.read()
                audio_duration = len(audio_data) / 16000  # rough estimate

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
            from IPython.display import HTML
            print("🎬 Playing the created video:")
            HTML(f"""
            <video width="640" height="360" controls>
                <source src="file://{output_path}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            """)

            return output_path

        except subprocess.CalledProcessError as e:
            print(f"🛑 Error creating video: {e}")
            print(f"FFmpeg stderr: {e.stderr.decode()}")

            # If FFmpeg is not installed or fails, just display the images
            print("\n⚠️ Video creation failed. Displaying images instead:")
            for img_path in resized_images:
                from IPython.display import Image
                Image(filename=img_path)
                
            return None
    else:
        print("⚠️ No images available for video creation.")
        return None
