#!/usr/bin/env python3
"""
Advanced Roblox Asset Uploader
High-performance uploader with smart retry logic, progress tracking, and comprehensive error handling.
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
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any, Union, NamedTuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
import threading
from queue import Queue, Empty
import signal

# Configuration constants
CONFIG_FILE = "config.json"
BASE_FOLDER = "IMAGES_TO_UPLOAD"
TEMP_FOLDER = "temp"
CACHE_FOLDER = "cache"
BACKUP_FOLDER = "backups"
PNG_EXTENSION = ".png"
MAX_NAME_LENGTH = 50
DEFAULT_PRICE = 5
DEFAULT_SLEEP_TIME = 15
MAX_RETRIES = 5  # Increased for better reliability
RETRY_DELAY = 3
CHUNK_SIZE = 8192  # For file operations
MAX_FILE_SIZE_MB = 10  # Maximum file size in MB

# Asset type mappings with validation
SUPPORTED_ASSET_TYPES = {
    "SHIRTS": "shirt",
    "PANTS": "pants",
    "TSHIRTS": "tshirt"  # Added T-shirt support
}

# Upload status tracking
class UploadStatus(Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    LISTING = "listing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class UploadResult:
    """Enhanced result tracking for uploads."""
    file_path: str
    asset_name: str
    status: UploadStatus
    asset_id: Optional[int] = None
    error_message: Optional[str] = None
    upload_time: Optional[float] = None
    file_size: Optional[int] = None
    attempt_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class UploadStats:
    """Statistics tracking for upload operations."""
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_size_mb: float = 0.0
    total_time: float = 0.0
    average_time_per_upload: float = 0.0
    throughput_mb_per_sec: float = 0.0

class SmartRateLimiter:
    """Intelligent rate limiter that adapts to API responses."""
    
    def __init__(self, initial_delay: float = 1.0, max_delay: float = 60.0):
        self.delay = initial_delay
        self.max_delay = max_delay
        self.min_delay = initial_delay
        self.last_request_time = 0
        self.consecutive_successes = 0
        self.lock = threading.Lock()
        
    def wait(self):
        """Wait based on current rate limit settings."""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.delay:
                sleep_time = self.delay - time_since_last
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()
    
    def handle_success(self):
        """Decrease delay after successful requests."""
        with self.lock:
            self.consecutive_successes += 1
            if self.consecutive_successes >= 3:  # After 3 successes, reduce delay
                self.delay = max(self.delay * 0.9, self.min_delay)
                self.consecutive_successes = 0
    
    def handle_rate_limit(self, retry_after: Optional[int] = None):
        """Increase delay when rate limited."""
        with self.lock:
            if retry_after:
                self.delay = min(retry_after + 1, self.max_delay)
            else:
                self.delay = min(self.delay * 2, self.max_delay)
            self.consecutive_successes = 0
            logger.warning(f"Rate limited! Increased delay to {self.delay:.2f}s")
    
    def handle_error(self):
        """Handle general errors."""
        with self.lock:
            self.consecutive_successes = 0

class ProgressTracker:
    """Thread-safe progress tracking with real-time updates."""
    
    def __init__(self, total_items: int):
        self.total_items = total_items
        self.completed_items = 0
        self.failed_items = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.results: List[UploadResult] = []
    
    def update(self, result: UploadResult):
        """Update progress with a new result."""
        with self.lock:
            self.results.append(result)
            if result.status == UploadStatus.SUCCESS:
                self.completed_items += 1
            elif result.status == UploadStatus.FAILED:
                self.failed_items += 1
            
            self._log_progress()
    
    def _log_progress(self):
        """Log current progress."""
        processed = self.completed_items + self.failed_items
        if processed > 0:
            elapsed = time.time() - self.start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (self.total_items - processed) / rate if rate > 0 else 0
            
            logger.info(
                f"Progress: {processed}/{self.total_items} "
                f"({processed/self.total_items*100:.1f}%) - "
                f"Success: {self.completed_items}, Failed: {self.failed_items} - "
                f"Rate: {rate:.2f}/min, ETA: {eta/60:.1f}min"
            )
    
    def get_stats(self) -> UploadStats:
        """Generate comprehensive statistics."""
        with self.lock:
            total_time = time.time() - self.start_time
            successful_results = [r for r in self.results if r.status == UploadStatus.SUCCESS]
            
            total_size_mb = sum(r.file_size or 0 for r in self.results) / (1024 * 1024)
            avg_time = sum(r.upload_time or 0 for r in successful_results) / len(successful_results) if successful_results else 0
            throughput = total_size_mb / total_time if total_time > 0 else 0
            
            return UploadStats(
                total_files=self.total_items,
                successful=self.completed_items,
                failed=self.failed_items,
                skipped=len([r for r in self.results if r.status == UploadStatus.SKIPPED]),
                total_size_mb=total_size_mb,
                total_time=total_time,
                average_time_per_upload=avg_time,
                throughput_mb_per_sec=throughput
            )

class FileValidator:
    """Validates files before upload."""
    
    @staticmethod
    def validate_image(file_path: str) -> Tuple[bool, Optional[str]]:
        """Validate image file for upload."""
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                return False, f"File too large ({file_size/(1024*1024):.1f}MB > {MAX_FILE_SIZE_MB}MB)"
            
            if file_size == 0:
                return False, "File is empty"
            
            # Check file extension
            if not file_path.lower().endswith(PNG_EXTENSION):
                return False, f"Invalid file type (must be {PNG_EXTENSION})"
            
            # Try to read first few bytes to verify it's a valid PNG
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if header != b'\x89PNG\r\n\x1a\n':
                    return False, "Invalid PNG file format"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {e}"

class BackupManager:
    """Manages backups of successfully uploaded files."""
    
    def __init__(self, backup_enabled: bool = True):
        self.backup_enabled = backup_enabled
        if backup_enabled:
            os.makedirs(BACKUP_FOLDER, exist_ok=True)
    
    def backup_file(self, original_path: str, asset_id: int) -> bool:
        """Backup a successfully uploaded file."""
        if not self.backup_enabled:
            return True
            
        try:
            filename = os.path.basename(original_path)
            name, ext = os.path.splitext(filename)
            backup_name = f"{name}_{asset_id}_{int(time.time())}{ext}"
            backup_path = os.path.join(BACKUP_FOLDER, backup_name)
            
            shutil.copy2(original_path, backup_path)
            logger.debug(f"Backed up {filename} to {backup_name}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to backup {original_path}: {e}")
            return False

# Enhanced logging setup
class ColoredFormatter(logging.Formatter):
    """Colored log formatter for better visibility."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

def setup_logging():
    """Setup enhanced logging with colors and file rotation."""
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    
    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        "logs/uploader.log", 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    
    # Setup root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

# Custom exceptions with more detail
class ConfigError(Exception):
    """Configuration-related errors."""
    pass

class AssetUploadError(Exception):
    """Asset upload-specific errors."""
    def __init__(self, message: str, error_code: Optional[str] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after

class ValidationError(Exception):
    """File validation errors."""
    pass

def load_enhanced_config() -> Dict[str, Any]:
    """Load and validate enhanced configuration."""
    try:
        config_path = Path(CONFIG_FILE)
        if not config_path.exists():
            logger.warning(f"Config file {CONFIG_FILE} not found. Creating default config.")
            default_config = {
                "ROBLOSECURITY": "",
                "group_id": 0,
                "description": "",
                "assets_price": DEFAULT_PRICE,
                "name_tags": [],
                "sleep_each_upload": DEFAULT_SLEEP_TIME,
                "parallel_uploads": False,
                "max_workers": 3,
                "enable_backup": True,
                "auto_retry": True,
                "smart_rate_limiting": True,
                "progress_tracking": True,
                "file_validation": True,
                "max_file_size_mb": MAX_FILE_SIZE_MB,
                "supported_formats": [".png"],
                "batch_size": 50,
                "enable_caching": True
            }
            
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            
            raise ConfigError("Default config created. Please update config.json with your settings.")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        required_fields = ["ROBLOSECURITY", "group_id"]
        for field in required_fields:
            if not config.get(field):
                raise ConfigError(f"Required field '{field}' missing or empty in config.json")
        
        # Set defaults for optional fields
        defaults = {
            "description": "",
            "assets_price": DEFAULT_PRICE,
            "name_tags": [],
            "sleep_each_upload": DEFAULT_SLEEP_TIME,
            "parallel_uploads": False,
            "max_workers": 3,
            "enable_backup": True,
            "auto_retry": True,
            "smart_rate_limiting": True,
            "progress_tracking": True,
            "file_validation": True,
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "supported_formats": [".png"],
            "batch_size": 50,
            "enable_caching": True
        }
        
        for key, default_value in defaults.items():
            config.setdefault(key, default_value)
        
        # Validate configuration values
        if config["max_workers"] < 1 or config["max_workers"] > 10:
            logger.warning("max_workers should be between 1-10. Using default: 3")
            config["max_workers"] = 3
        
        if config["assets_price"] < 0:
            logger.warning("assets_price cannot be negative. Using default: 5")
            config["assets_price"] = DEFAULT_PRICE
        
        return config
        
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config.json: {e}")
    except Exception as e:
        raise ConfigError(f"Error loading config: {e}")

def get_enhanced_images_to_upload(base_folder: str = BASE_FOLDER, config: Optional[Dict[str, Any]] = None) -> List[Tuple[str, str]]:
    """Enhanced image discovery with validation and caching."""
    images_and_types = []
    config = config or {}
    
    if not os.path.isdir(base_folder):
        logger.info(f"Creating base folder: {base_folder}")
        os.makedirs(base_folder, exist_ok=True)
    
    validator = FileValidator()
    supported_formats = config.get("supported_formats", [PNG_EXTENSION])
    
    logger.info("Scanning for uploadable images...")
    
    for folder_name, asset_type in SUPPORTED_ASSET_TYPES.items():
        current_path = Path(base_folder) / folder_name
        
        if not current_path.exists():
            logger.info(f"Creating subfolder: {current_path}")
            current_path.mkdir(exist_ok=True)
            continue
        
        # Find all supported image files
        image_files = []
        for format_ext in supported_formats:
            pattern = f"*{format_ext}"
            image_files.extend(current_path.glob(pattern))
        
        if image_files:
            logger.info(f"Found {len(image_files)} potential files in '{folder_name}' folder")
            
            valid_files = 0
            for file_path in image_files:
                if config.get("file_validation", True):
                    is_valid, error_msg = validator.validate_image(str(file_path))
                    if not is_valid:
                        logger.warning(f"Skipping {file_path.name}: {error_msg}")
                        continue
                
                images_and_types.append((str(file_path), asset_type))
                valid_files += 1
            
            logger.info(f"Validated {valid_files} files in '{folder_name}' folder")
        else:
            logger.info(f"No supported files found in '{folder_name}' folder")
    
    if not images_and_types:
        logger.warning(f"No valid images found. Check folders: {list(SUPPORTED_ASSET_TYPES.keys())}")
        return []
    
    logger.info(f"Total files ready for upload: {len(images_and_types)}")
    return images_and_types

def generate_enhanced_name(file_path: str, tags_to_add: Optional[List[str]] = None, max_length: int = MAX_NAME_LENGTH) -> str:
    """Enhanced name generation with better cleaning and tag optimization."""
    tags_to_add = tags_to_add or []
    
    # Extract base name
    file_path_obj = Path(file_path)
    base_name = file_path_obj.stem
    
    # Enhanced cleaning
    # Remove common prefixes/suffixes
    prefixes_to_remove = ["roblox_", "shirt_", "pants_", "asset_"]
    suffixes_to_remove = ["_final", "_export", "_upload", "_ready"]
    
    clean_name = base_name.lower()
    for prefix in prefixes_to_remove:
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):]
            break
    
    for suffix in suffixes_to_remove:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)]
            break
    
    # Replace separators with spaces
    clean_name = re.sub(r'[_\-\.]+', ' ', clean_name)
    
    # Remove special characters but keep alphanumeric and spaces
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', clean_name)
    
    # Normalize whitespace
    clean_name = ' '.join(clean_name.split())
    
    # Capitalize words properly
    clean_name = ' '.join(word.capitalize() for word in clean_name.split())
    
    # Add tags intelligently
    if tags_to_add:
        base_length = len(clean_name)
        available_space = max_length - base_length - 2  # Reserve space for ", "
        
        added_tags = []
        for tag in tags_to_add:
            tag_with_sep = f", {tag}" if added_tags else f" {tag}"
            if len(''.join(added_tags) + tag_with_sep) <= available_space:
                added_tags.append(tag_with_sep)
            else:
                break
        
        if added_tags:
            clean_name += ''.join(added_tags)
    
    # Final length check
    if len(clean_name) > max_length:
        clean_name = clean_name[:max_length].rstrip()
    
    return clean_name or "Untitled Asset"

def create_optimized_temp_file(original_path: str, asset_type: str) -> str:
    """Create optimized temporary file with better organization."""
    temp_folder = Path(TEMP_FOLDER) / f"{asset_type}s"
    temp_folder.mkdir(parents=True, exist_ok=True)
    
    # Generate unique temp filename to avoid conflicts
    original_name = Path(original_path).name
    timestamp = int(time.time())
    temp_name = f"{timestamp}_{original_name}"
    temp_path = temp_folder / temp_name
    
    try:
        # Use efficient copy with chunk reading for large files
        with open(original_path, 'rb') as src, open(temp_path, 'wb') as dst:
            while chunk := src.read(CHUNK_SIZE):
                dst.write(chunk)
        
        return str(temp_path)
        
    except Exception as e:
        logger.error(f"Failed to create temp file: {e}")
        raise

def enhanced_upload_asset(
    asset_name: str,
    temp_path: str,
    asset_type: str,
    cookie: Any,
    group_id: int,
    description: str,
    price: int,
    rate_limiter: SmartRateLimiter,
    max_retries: int = MAX_RETRIES
) -> UploadResult:
    """Enhanced asset upload with smart retry and rate limiting."""
    file_size = os.path.getsize(temp_path)
    result = UploadResult(
        file_path=temp_path,
        asset_name=asset_name,
        status=UploadStatus.PENDING,
        file_size=file_size
    )
    
    for attempt in range(max_retries):
        try:
            result.attempt_count = attempt + 1
            result.status = UploadStatus.UPLOADING
            
            logger.debug(f"Upload attempt {attempt + 1}/{max_retries} for '{asset_name}'")
            
            # Rate limiting
            rate_limiter.wait()
            
            upload_start = time.time()
            
            # Call the upload function
            upload_response = src.upload.create_asset(
                asset_name, temp_path, asset_type, cookie, 
                group_id, description, price, price
            )
            
            if isinstance(upload_response, dict) and 'response' in upload_response:
                asset_id = upload_response['response'].get('assetId')
                if asset_id:
                    result.asset_id = asset_id
                    result.status = UploadStatus.PROCESSING
                    result.upload_time = time.time() - upload_start
                    
                    # Handle the listing part
                    if price > 0:
                        result.status = UploadStatus.LISTING
                        if release_enhanced_asset(cookie, asset_id, price, asset_name, description, group_id, rate_limiter):
                            result.status = UploadStatus.SUCCESS
                            rate_limiter.handle_success()
                            logger.info(f"✓ Successfully uploaded and listed: {asset_name} (ID: {asset_id})")
                            return result
                        else:
                            result.status = UploadStatus.FAILED
                            result.error_message = "Upload successful but listing failed"
                    else:
                        result.status = UploadStatus.SUCCESS
                        rate_limiter.handle_success()
                        logger.info(f"✓ Successfully uploaded: {asset_name} (ID: {asset_id})")
                        return result
            
            # Handle specific error responses
            if upload_response == 2:
                result.status = UploadStatus.FAILED
                result.error_message = "Insufficient funds"
                logger.error(f"✗ Insufficient funds for {asset_name}")
                return result
            elif upload_response == 3:
                result.status = UploadStatus.FAILED
                result.error_message = "Unauthorized"
                logger.error(f"✗ Unauthorized access for {asset_name}")
                return result
            
            # Generic failure
            rate_limiter.handle_error()
            error_msg = f"Upload failed with response: {upload_response}"
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limited
                retry_after = int(e.response.headers.get('Retry-After', 60))
                rate_limiter.handle_rate_limit(retry_after)
                error_msg = f"Rate limited (retry after {retry_after}s)"
            else:
                rate_limiter.handle_error()
                error_msg = f"HTTP error {e.response.status_code}: {e}"
                
        except Exception as e:
            rate_limiter.handle_error()
            error_msg = f"Unexpected error: {e}"
        
        if attempt < max_retries - 1:
            delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
            logger.warning(f"⚠ {error_msg}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
        else:
            logger.error(f"✗ All upload attempts failed for {asset_name}: {error_msg}")
    
    result.status = UploadStatus.FAILED
    result.error_message = error_msg
    return result

def release_enhanced_asset(
    cookie: Any,
    asset_id: int,
    price: int,
    asset_name: str,
    description: str,
    group_id: int,
    rate_limiter: SmartRateLimiter,
    max_retries: int = 3
) -> bool:
    """Enhanced asset release with retry logic."""
    for attempt in range(max_retries):
        try:
            rate_limiter.wait()
            
            response = src.upload.release_asset(cookie, asset_id, price, asset_name, description, group_id)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("status") == 0:
                    rate_limiter.handle_success()
                    return True
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 30))
                rate_limiter.handle_rate_limit(retry_after)
            else:
                rate_limiter.handle_error()
            
        except Exception as e:
            rate_limiter.handle_error()
            logger.warning(f"Release attempt {attempt + 1} failed: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))
    
    return False

def process_enhanced_single_asset(
    file_info: Tuple[str, str],
    cookie: Any,
    config: Dict[str, Any],
    rate_limiter: SmartRateLimiter,
    backup_manager: BackupManager
) -> UploadResult:
    """Enhanced single asset processing with comprehensive error handling."""
    original_path, asset_type = file_info
    temp_path = None
    
    try:
        # Generate asset name
        asset_name = generate_enhanced_name(
            original_path, 
            config.get("name_tags", []),
            config.get("max_name_length", MAX_NAME_LENGTH)
        )
        
        if not asset_name or asset_name == "Untitled Asset":
            return UploadResult(
                file_path=original_path,
                asset_name="",
                status=UploadStatus.SKIPPED,
                error_message="Could not generate valid asset name"
            )
        
        # Create temporary file
        temp_path = create_optimized_temp_file(original_path, asset_type)
        
        # Upload the asset
        result = enhanced_upload_asset(
            asset_name=asset_name,
            temp_path=temp_path,
            asset_type=asset_type,
            cookie=cookie,
            group_id=config["group_id"],
            description=config.get("description", ""),
            price=config.get("assets_price", DEFAULT_PRICE),
            rate_limiter=rate_limiter,
            max_retries=config.get("max_retries", MAX_RETRIES)
        )
        
        # Update result with original path
        result.file_path = original_path
        
        # Backup successful uploads
        if result.status == UploadStatus.SUCCESS and result.asset_id:
            backup_manager.backup_file(original_path, result.asset_id)
        
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error processing {os.path.basename(original_path)}: {e}", exc_info=True)
        return UploadResult(
            file_path=original_path,
            asset_name=asset_name if 'asset_name' in locals() else "",
            status=UploadStatus.FAILED,
            error_message=f"Processing error: {e}"
        )
    
    finally:
        # Cleanup temporary file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_path}: {e}")

def process_assets_enhanced_parallel(
    images_to_process: List[Tuple[str, str]],
    cookie: Any,
    config: Dict[str, Any],
    progress_tracker: ProgressTracker
) -> List[UploadResult]:
    """Enhanced parallel processing with smart rate limiting and progress tracking."""
    max_workers = min(config.get("max_workers", 3), len(images_to_process))
    rate_limiter = SmartRateLimiter(
        initial_delay=config.get("sleep_each_upload", DEFAULT_SLEEP_TIME) / max_workers,
        max_delay=60.0
    )
    backup_manager = BackupManager(config.get("enable_backup", True))
    
    results = []
    
    logger.info(f"Starting parallel processing with {max_workers} workers")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(
                process_enhanced_single_asset,
                file_info,
                cookie,
                config,
                rate_limiter,
                backup_manager
            ): file_info for file_info in images_to_process
        }
        
        # Process completed tasks
        for future in as_completed(future_to_file):
            try:
                result = future.result()
                results.append(result)
                progress_tracker.update(result)
                
            except Exception as e:
                file_info = future_to_file[future]
                error_result = UploadResult(
                    file_path=file_info[0],
                    asset_name="",
                    status=UploadStatus.FAILED,
                    error_message=f"Task execution error: {e}"
                )
                results.append(error_result)
                progress_tracker.update(error_result)
    
    return results

def process_assets_enhanced_sequential(
    images_to_process: List[Tuple[str, str]],
    cookie: Any,
    config: Dict[str, Any],
    progress_tracker: ProgressTracker
) -> List[UploadResult]:
    """Enhanced sequential processing with detailed progress tracking."""
    rate_limiter = SmartRateLimiter(
        initial_delay=config.get("sleep_each_upload", DEFAULT_SLEEP_TIME),
        max_delay=60.0
    )
    backup_manager = BackupManager(config.get("enable_backup", True))
    
    results = []
    
    logger.info("Starting sequential processing")
    
    for i, file_info in enumerate(images_to_process, 1):
        logger.info(f"Processing {i}/{len(images_to_process)}: {os.path.basename(file_info[0])}")
        
        result = process_enhanced_single_asset(
            file_info, cookie, config, rate_limiter, backup_manager
        )
        
        results.append(result)
        progress_tracker.update(result)
    
    return results

def generate_detailed_report(results: List[UploadResult], stats: UploadStats, config: Dict[str, Any]):
    """Generate a comprehensive upload report."""
    report_lines = [
        "\n" + "="*80,
        "UPLOAD REPORT",
        "="*80,
        f"Total Files Processed: {stats.total_files}",
        f"Successful Uploads: {stats.successful}",
        f"Failed Uploads: {stats.failed}",
        f"Skipped Files: {stats.skipped}",
        f"Success Rate: {(stats.successful/stats.total_files*100):.1f}%" if stats.total_files > 0 else "Success Rate: 0%",
        f"Total Data Processed: {stats.total_size_mb:.2f} MB",
        f"Total Time: {stats.total_time:.2f} seconds",
        f"Average Time per Upload: {stats.average_time_per_upload:.2f} seconds",
        f"Throughput: {stats.throughput_mb_per_sec:.3f} MB/s",
        "="*80
    ]
    
    # Failed uploads details
    failed_results = [r for r in results if r.status == UploadStatus.FAILED]
    if failed_results:
        report_lines.extend([
            "\nFAILED UPLOADS:",
            "-" * 40
        ])
        for result in failed_results:
            filename = os.path.basename(result.file_path)
            report_lines.append(f"• {filename}: {result.error_message}")
    
    # Successful uploads summary
    successful_results = [r for r in results if r.status == UploadStatus.SUCCESS]
    if successful_results:
        report_lines.extend([
            f"\nSUCCESSFUL UPLOADS ({len(successful_results)}):",
            "-" * 40
        ])
        for result in successful_results[:10]:  # Show first 10
            filename = os.path.basename(result.file_path)
            report_lines.append(f"• {filename} → ID: {result.asset_id}")
        
        if len(successful_results) > 10:
            report_lines.append(f"... and {len(successful_results) - 10} more")
    
    report_lines.append("="*80)
    
    # Log the report
    for line in report_lines:
        logger.info(line)
    
    # Save to file
    try:
        report_path = f"logs/upload_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, 'w') as f:
            f.write('\n'.join(report_lines))
        logger.info(f"Detailed report saved to: {report_path}")
    except Exception as e:
        logger.warning(f"Failed to save report file: {e}")

def setup_signal_handlers():
    """Setup graceful shutdown handlers."""
    def signal_handler(signum, frame):
        logger.warning(f"Received signal {signum}. Initiating graceful shutdown...")
        # Set a global flag that can be checked in main loops
        global shutdown_requested
        shutdown_requested = True
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# Global shutdown flag
shutdown_requested = False

def main():
    """Enhanced main function with comprehensive error handling and reporting."""
    setup_signal_handlers()
    
    try:
        logger.info("🚀 Starting Enhanced Roblox Asset Uploader")
        
        # Load configuration
        config = load_enhanced_config()
        logger.info("✓ Configuration loaded successfully")
        
        # Initialize cookie
        cookie = src.cookie.cookie(config["ROBLOSECURITY"])
        logger.info("✓ Authentication initialized")
        
        # Discover images
        images_to_process = get_enhanced_images_to_upload(BASE_FOLDER, config)
        if not images_to_process:
            logger.warning("No images found to upload. Exiting.")
            return
        
        # Initialize progress tracking
        progress_tracker = ProgressTracker(len(images_to_process))
        
        # Process uploads
        start_time = time.time()
        
        if config.get("parallel_uploads", False) and len(images_to_process) > 1:
            results = process_assets_enhanced_parallel(
                images_to_process, cookie, config, progress_tracker
            )
        else:
            results = process_assets_enhanced_sequential(
                images_to_process, cookie, config, progress_tracker
            )
        
        # Generate final statistics and report
        stats = progress_tracker.get_stats()
        generate_detailed_report(results, stats, config)
        
        # Success message
        if stats.successful > 0:
            logger.info(f"🎉 Upload session completed! {stats.successful}/{stats.total_files} files processed successfully")
        else:
            logger.warning("⚠️ No files were uploaded successfully")
        
    except ConfigError as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("⚠️ Upload interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("🔄 Cleanup completed. Goodbye!")

if __name__ == "__main__":
    main()