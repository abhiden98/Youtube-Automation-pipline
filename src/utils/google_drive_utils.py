import os
import requests
import tempfile
import datetime
import shutil

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
            shutil.rmtree(temp_dir)
        except:
            pass

def upload_text_file_to_drive(content, filename, parent_folder_id, drive_service):
    """Upload a text file to Google Drive using a temporary file approach.
    
    Args:
        content: The text content to upload
        filename: The name of the file in Google Drive
        parent_folder_id: The ID of the parent folder
        drive_service: The Google Drive service object
        
    Returns:
        The file ID of the uploaded file
    """
    from googleapiclient.http import MediaFileUpload
    
    # Create file metadata
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id]
    }
    
    # Create a temporary file
    temp_dir = tempfile.mkdtemp()
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
    
    # Clean up
    try:
        shutil.rmtree(temp_dir)
    except:
        pass
    
    return file.get('id')
