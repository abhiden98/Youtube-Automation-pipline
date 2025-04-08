import os
import datetime
import sys
import base64
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from IPython.display import HTML

from src.utils.google_drive_utils import download_file_from_google_drive, upload_text_file_to_drive

def upload_to_google_drive(output_path, story_text, image_files, metadata, thumbnail_path, temp_dir):
    """
    Uploads the generated video and associated metadata to Google Drive.
    
    Args:
        output_path: Path to the video file
        story_text: The complete story text
        image_files: List of images from the story
        metadata: The SEO metadata dictionary
        thumbnail_path: Path to the thumbnail image
        temp_dir: Temporary directory for intermediate files
        
    Returns:
        None
    """
    try:
        print("\n--- Saving Video to Google Drive using API ---")

        # Import necessary libraries for Google Drive API
        try:
            # Download and use credentials from Google Drive link instead of hardcoding them
            credentials_file_id = "152LtocR_Lvll37IW3GXJWAowLS02YBF2"
            credentials_file_path = os.path.join(temp_dir, "drive_credentials.json")
            
            print("⏳ Downloading Google Drive API credentials from the provided link...")
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
        
        # Upload metadata files
        # Title
        title_content = metadata['title']
        title_file_id = upload_text_file_to_drive(title_content, 'title.txt', story_folder_id, drive_service)

        # Description
        desc_content = metadata['description']
        desc_file_id = upload_text_file_to_drive(desc_content, 'description.txt', story_folder_id, drive_service)

        # Tags
        tags_content = '\n'.join(metadata['tags'])
        tags_file_id = upload_text_file_to_drive(tags_content, 'tags.txt', story_folder_id, drive_service)

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
        
        # Provide direct download option
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
