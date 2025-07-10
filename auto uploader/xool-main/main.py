#!/usr/bin/env python3
"""
Automated Roblox Asset Uploader
Uploads PNG files from SHIRTS and PANTS folders to Roblox with optimized performance.
"""

import src
import time
import json
import os
import re
import shutil
import logging
import sys
import requests
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration constants
CONFIG_FILE = "config.json"
BASE_FOLDER = "IMAGES_TO_UPLOAD"
TEMP_FOLDER = "temp"
PNG_EXTENSION = ".png"
MAX_NAME_LENGTH = 50
DEFAULT_PRICE = 5
DEFAULT_SLEEP_TIME = 20  # Reduced default sleep time
MAX_RETRIES = 3
RETRY_DELAY = 5

# Asset type mappings
SUPPORTED_ASSET_TYPES = {
    "SHIRTS": "shirt",
    "PANTS": "pants"
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uploader.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Custom exceptions
class ConfigError(Exception):
    """Raised when there's an issue with configuration."""
    pass

class AssetUploadError(Exception):
    """Raised when asset upload fails."""
    pass

class OptimizedSession:
    """Optimized session manager for HTTP requests."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def get_session(self):
        return self.session
        
    def close(self):
        self.session.close()

def load_config() -> Dict[str, Any]:
    """
    Load and validate configuration from config.json.
    
    Returns:
        Dict[str, Any]: Validated configuration dictionary
        
    Raises:
        ConfigError: If configuration is invalid or missing required fields
    """
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            
        # Validate required fields
        if not config.get("ROBLOSECURITY"):
            raise ConfigError("'ROBLOSECURITY' key not found in config.json")
            
        if not config.get("group_id"):
            raise ConfigError("'group_id' not found in config.json")
            
        # Set defaults for optional fields
        config.setdefault("description", "")
        config.setdefault("assets_price", DEFAULT_PRICE)
        config.setdefault("name_tags", [])
        config.setdefault("sleep_each_upload", DEFAULT_SLEEP_TIME)
        config.setdefault("parallel_uploads", False)  # New option for parallel processing
        config.setdefault("max_workers", 3)  # Conservative default for parallel uploads
        
        return config
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ConfigError(f"Error with config.json: {e}")

def get_images_to_upload(base_folder: str = BASE_FOLDER) -> List[Tuple[str, str]]:
    """
    Finds all .png files in SHIRTS and PANTS subfolders.
    
    Args:
        base_folder: Base folder containing SHIRTS and PANTS subfolders
        
    Returns:
        List of tuples, where each tuple is (file_path, asset_type)
    """
    images_and_types = []

    if not os.path.isdir(base_folder):
        logger.info(f"Main folder '{base_folder}' not found. Creating it now.")
        os.makedirs(base_folder)

    logger.info("Checking for images in specified subfolders")
    for folder_name, asset_type in SUPPORTED_ASSET_TYPES.items():
        current_path = os.path.join(base_folder, folder_name)
        
        if not os.path.isdir(current_path):
            logger.info(f"Subfolder '{folder_name}' not found. Creating it.")
            os.makedirs(current_path)
            logger.info(f"Please add your {asset_type.upper()} PNG files to the '{current_path}' folder.")
            continue

        image_files = [f for f in os.listdir(current_path) if f.lower().endswith(PNG_EXTENSION)]
        
        if image_files:
            logger.info(f"Found {len(image_files)} image(s) in '{folder_name}' folder.")
            for filename in image_files:
                full_path = os.path.join(current_path, filename)
                images_and_types.append((full_path, asset_type))
        else:
            logger.info(f"No {PNG_EXTENSION} files found in the '{folder_name}' folder.")
    
    if not images_and_types:
        logger.warning(f"No images found to upload. Please check your '{base_folder}/SHIRTS' and '{base_folder}/PANTS' folders.")
        return []

    logger.info(f"Found a total of {len(images_and_types)} image(s) to upload.")
    return images_and_types

def generate_clean_name(file_path: str, tags_to_add: List[str] = []) -> str:
    """
    Generates a clean asset name from a filename and appends tags if space allows.
    
    Args:
        file_path: Path to the image file
        tags_to_add: List of tags to append to the name, in priority order
        
    Returns:
        Clean name with tags, truncated to MAX_NAME_LENGTH if necessary
    """
    # No need to check for None since we're using an empty list as default
    filename = os.path.basename(file_path)
    name_without_ext, _ = os.path.splitext(filename)
    clean_name = name_without_ext.replace('_', ' ').replace('-', ' ')
    clean_name = re.sub(r'[^a-zA-Z0-9 ]', '', clean_name)
    clean_name = " ".join(clean_name.split()).strip()

    if len(clean_name) > MAX_NAME_LENGTH:
        return clean_name[:MAX_NAME_LENGTH]

    for tag in tags_to_add:
        potential_name = f"{clean_name}, {tag}"
        if len(potential_name) <= MAX_NAME_LENGTH:
            clean_name = potential_name
        else:
            break 
            
    return clean_name

def prepare_temp_file(original_path: str, asset_type: str) -> str:
    """
    Prepares a temporary copy of the image file for upload.
    
    Args:
        original_path: Path to the original image file
        asset_type: Type of asset ("shirt" or "pants")
        
    Returns:
        Path to the temporary file
        
    Raises:
        IOError: If file operations fail
    """
    temp_folder = os.path.join(TEMP_FOLDER, f"{asset_type}s")
    os.makedirs(temp_folder, exist_ok=True)
    
    temp_path = os.path.join(temp_folder, os.path.basename(original_path))
    try:
        shutil.copy(original_path, temp_path)
        return temp_path
    except IOError as e:
        logger.error(f"Failed to copy file to temp location: {e}")
        raise

def upload_asset(
    asset_name: str, 
    temp_path: str, 
    asset_type: str, 
    cookie: Any, 
    group_id: int, 
    description: str, 
    price: int
) -> int:
    """
    Uploads an asset to Roblox and returns the asset ID.
    
    Args:
        asset_name: Name of the asset
        temp_path: Path to the temporary image file
        asset_type: Type of asset ("shirt" or "pants")
        cookie: Roblox authentication cookie
        group_id: ID of the group to upload to
        description: Asset description
        price: Asset price
        
    Returns:
        The new asset ID
        
    Raises:
        AssetUploadError: If upload fails
    """
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Uploading '{asset_name}' (Type: {asset_type.upper()}) - Attempt {attempt + 1}/{MAX_RETRIES}")
            item_uploaded = src.upload.create_asset(asset_name, temp_path, asset_type, cookie, group_id, description, price, price)
            
            if not isinstance(item_uploaded, dict):
                raise AssetUploadError(f"Failed to upload '{asset_name}'. Reason code: {item_uploaded}")
                
            if 'response' not in item_uploaded or 'assetId' not in item_uploaded['response']:
                raise AssetUploadError(f"Failed to upload '{asset_name}'. Invalid response format: {item_uploaded}")
                
            new_asset_id = item_uploaded['response']['assetId']
            logger.info(f"Successfully uploaded. New Asset ID: {new_asset_id}")
            return new_asset_id
            
        except AssetUploadError as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                logger.warning(f"{e}. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"All upload attempts failed: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
            raise AssetUploadError(f"Unexpected error: {e}")
    
    # This should never be reached as the loop will either return or raise an exception
    raise AssetUploadError("Failed to upload asset after all retries")

def release_asset_for_sale(
    cookie: Any, 
    asset_id: int, 
    price: int, 
    asset_name: str, 
    description: str, 
    group_id: int
) -> bool:
    """
    Puts an asset on sale.
    
    Args:
        cookie: Roblox authentication cookie
        asset_id: ID of the asset to put on sale
        price: Price in Robux
        asset_name: Name of the asset
        description: Asset description
        group_id: ID of the group
        
    Returns:
        True if successful, False otherwise
    """
    if price <= 0:
        logger.info("Price is 0, item will not be put on sale.")
        return True
        
    logger.info(f"Putting asset on sale for {price} R$...")
    
    for attempt in range(MAX_RETRIES):
        try:
            release_response = src.upload.release_asset(cookie, asset_id, price, asset_name, description, group_id)
            
            if release_response.status_code == 200 and release_response.json().get("status") == 0:
                logger.info("Successfully released item for sale!")
                return True
            else:
                error_msg = f"Failed to release item. Status: {release_response.status_code}, Response: {release_response.text}"
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"{error_msg} Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"All release attempts failed: {error_msg}")
                    return False
                    
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Error releasing asset: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"All release attempts failed due to unexpected error: {e}")
                return False
    
    return False

def process_single_asset(
    original_path: str, 
    asset_type: str, 
    cookie: Any, 
    group_id: int, 
    description: str, 
    price: int, 
    name_tags: List[str],
    sleep_time: float = 0
) -> Tuple[bool, Optional[str]]:
    """
    Process a single asset from start to finish.
    
    Args:
        original_path: Path to the original image file
        asset_type: Type of asset ("shirt" or "pants")
        cookie: Roblox authentication cookie
        group_id: ID of the group to upload to
        description: Asset description
        price: Asset price
        name_tags: List of tags to append to the name
        sleep_time: Time to sleep after processing (for rate limiting)
        
    Returns:
        Tuple of (success, error_message)
    """
    temp_path = None
    asset_name = generate_clean_name(original_path, name_tags)
    
    if not asset_name:
        logger.warning(f"Skipping file '{os.path.basename(original_path)}' because it resulted in an empty name.")
        return False, "Empty name"
    
    try:
        temp_path = prepare_temp_file(original_path, asset_type)
        
        # Upload the asset
        asset_id = upload_asset(asset_name, temp_path, asset_type, cookie, group_id, description, price)
        
        # Put the asset on sale
        if not release_asset_for_sale(cookie, asset_id, price, asset_name, description, group_id):
            return False, "Failed to put on sale"
        
        # Sleep for rate limiting if specified
        if sleep_time > 0:
            time.sleep(sleep_time)
            
        return True, None
        
    except AssetUploadError as e:
        return False, str(e)
    except Exception as e:
        logger.error(f"Unexpected error processing '{os.path.basename(original_path)}': {e}", exc_info=True)
        return False, f"Unexpected error: {e}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_path}: {e}")

def process_assets_parallel(
    images_to_process: List[Tuple[str, str]],
    cookie: Any,
    group_id: int,
    description: str,
    price: int,
    name_tags: List[str],
    max_workers: int = 3
) -> Tuple[int, int, List[str]]:
    """
    Process assets in parallel with rate limiting.
    
    Returns:
        Tuple of (successful_uploads, failed_uploads, failed_upload_details)
    """
    successful_uploads = 0
    failed_uploads = 0
    failed_upload_details = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all upload tasks
        future_to_path = {
            executor.submit(
                process_single_asset,
                original_path, 
                asset_type, 
                cookie, 
                group_id, 
                description, 
                price, 
                name_tags,
                0  # No sleep in parallel mode, we'll handle rate limiting differently
            ): (original_path, asset_type) 
            for original_path, asset_type in images_to_process
        }
        
        # Process completed uploads
        for future in as_completed(future_to_path):
            original_path, asset_type = future_to_path[future]
            try:
                success, error = future.result()
                if success:
                    successful_uploads += 1
                    logger.info(f"✓ Completed: {os.path.basename(original_path)}")
                else:
                    failed_uploads += 1
                    asset_name = generate_clean_name(original_path, name_tags)
                    failed_upload_details.append(f"{asset_name} ({error})")
                    logger.error(f"✗ Failed: {os.path.basename(original_path)} - {error}")
            except Exception as e:
                failed_uploads += 1
                asset_name = generate_clean_name(original_path, name_tags)
                failed_upload_details.append(f"{asset_name} (Exception: {e})")
                logger.error(f"✗ Exception: {os.path.basename(original_path)} - {e}")
    
    return successful_uploads, failed_uploads, failed_upload_details

def main():
    """Main function to control the uploader."""
    session_manager = OptimizedSession()
    
    try:
        # Load and validate configuration
        config = load_config()
        
        cookie_str = config["ROBLOSECURITY"]
        cookie = src.cookie.cookie(cookie_str)
        group_id = config["group_id"]
        description = config["description"]
        price = config["assets_price"]
        name_tags = config["name_tags"]
        sleep_time = config["sleep_each_upload"]
        parallel_uploads = config.get("parallel_uploads", False)
        max_workers = config.get("max_workers", 3)
        
        if name_tags:
            logger.info(f"Found {len(name_tags)} tags to append to names. Order is determined by config.json.")
        
        # Get images to process
        images_to_process = get_images_to_upload(BASE_FOLDER)
        if not images_to_process:
            return
        
        logger.info("Starting upload process")
        start_time = time.time()
        
        if parallel_uploads and len(images_to_process) > 1:
            logger.info(f"Using parallel processing with {max_workers} workers")
            successful_uploads, failed_uploads, failed_upload_details = process_assets_parallel(
                images_to_process, cookie, group_id, description, price, name_tags, max_workers
            )
        else:
            logger.info("Using sequential processing")
            successful_uploads = 0
            failed_uploads = 0
            failed_upload_details = []
            
            # Process each image sequentially
            for i, (original_path, asset_type) in enumerate(images_to_process, 1):
                logger.info(f"Processing item {i} of {len(images_to_process)}: {os.path.basename(original_path)}")
                
                success, error = process_single_asset(
                    original_path, 
                    asset_type, 
                    cookie, 
                    group_id, 
                    description, 
                    price, 
                    name_tags,
                    sleep_time if i < len(images_to_process) else 0  # No sleep after last item
                )
                
                if success:
                    successful_uploads += 1
                else:
                    failed_uploads += 1
                    asset_name = generate_clean_name(original_path, name_tags)
                    failed_upload_details.append(f"{asset_name} ({error})")
        
        # Print summary
        elapsed_time = time.time() - start_time
        logger.info("Process Finished")
        logger.info(f"Total time: {elapsed_time:.2f} seconds")
        logger.info(f"Successful: {successful_uploads} | Failed: {failed_uploads}")
        
        if failed_upload_details:
            logger.info("Summary of Failed Uploads:")
            for detail in failed_upload_details:
                logger.info(f"- {detail}")
                
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}", exc_info=True)
    finally:
        session_manager.close()

if __name__ == "__main__":
    main()