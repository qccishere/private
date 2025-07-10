import requests
import os
import re
import argparse
import time
import string
import random
import json
import logging
from rich.console import Console
from PIL import Image
from io import BytesIO
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Setup ---
console = Console(highlight=False)
logging.basicConfig(
    filename='download.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class OptimizedSession:
    """Optimized session manager with connection pooling and reuse."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Connection pooling optimization
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def get_session(self):
        return self.session
    
    def close(self):
        self.session.close()

# Global session manager
session_manager = OptimizedSession()

# --- Helpers ---
def cprint(color, content):
    console.print(f"[bold {color}]{content}[/bold {color}]")
    logging.info(content)

def handle_request_errors(e, url):
    """Handles request exceptions with logging."""
    if isinstance(e, requests.HTTPError):
        message = f"HTTP Error {e.response.status_code} for {url}"
    elif isinstance(e, requests.ConnectionError):
        message = f"Connection Error for {url}"
    elif isinstance(e, requests.Timeout):
        message = f"Timeout for {url}"
    elif isinstance(e, requests.RequestException):
        message = f"Request failed for {url}: {e}"
    else:
        message = f"An unexpected error occurred for {url}: {e}"
    
    # Only log to file, don't print to console
    logging.error(message)

def make_request(method, url, max_retries=3, session=None, **kwargs):
    """Makes an HTTP request with exponential backoff and session reuse."""
    # For CSRF token requests, don't show errors in console
    is_csrf_request = url == "https://auth.roblox.com/v2/logout"
    
    # Use provided session or global session
    req_session = session or session_manager.get_session()
    
    for attempt in range(max_retries):
        try:
            response = req_session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            handle_request_errors(e, url)
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 10)  # Cap at 10 seconds
                if not is_csrf_request:
                    cprint('yellow', f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                if not is_csrf_request:
                    cprint('red', f"Max retries reached for {url}. Giving up.")
                return None
    return None

def load_settings():
    try:
        if os.path.exists('settings.json'):
            with open('settings.json', 'r') as f:
                return json.load(f)
    except Exception as e:
        cprint('yellow', f"Error loading settings: {e}")
    return {}

def save_settings(settings):
    try:
        with open('settings.json', 'w') as f:
            json.dump(settings, f, indent=4)
        cprint('green', "Settings saved successfully!")
    except Exception as e:
        cprint('red', f"Error saving settings: {e}")

def get_csrf_token(cookie, proxies, session=None):
    """Fetches a CSRF token from Roblox with session reuse."""
    if not cookie:
        return None
    
    try:
        response = make_request(
            "post",
            "https://auth.roblox.com/v2/logout",
            cookies={".ROBLOSECURITY": cookie},
            proxies=proxies,
            session=session
        )
        return response.headers.get("x-csrf-token") if response else None
    except Exception as e:
        logging.error(f"Error getting CSRF token: {e}")
        return None

def sanitize_filename(name):
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name

def get_asset_name(cookie, csrf_token, clothing_id, proxies, session=None):
    """Fetches the asset's name using the Roblox API with session reuse."""
    data_payload = {"items": [{"itemType": "Asset", "id": int(clothing_id)}]}
    response = make_request(
        "post",
        "https://catalog.roblox.com/v1/catalog/items/details",
        json=data_payload,
        cookies={".ROBLOSECURITY": cookie},
        headers={"x-csrf-token": csrf_token},
        proxies=proxies,
        timeout=10,
        session=session
    )
    if response:
        data = response.json()
        if data.get("data") and len(data["data"]) > 0:
            return data["data"][0].get("name", str(clothing_id))
    return str(clothing_id)

def get_asset_id(cookie, clothing_id, proxies, session=None):
    response = make_request(
        "get",
        f'https://assetdelivery.roblox.com/v1/assetId/{clothing_id}',
        cookies={".ROBLOSECURITY": cookie},
        proxies=proxies,
        timeout=10,
        session=session
    )
    if not response:
        return None
    data = response.json()
    if data.get("IsCopyrightProtected"):
        cprint('red', f"Copyright Protected! ID: {clothing_id}")
        logging.warning(f"Copyright Protected: {clothing_id}")
        return "ERROR"
    
    location = data.get('location')
    if location:
        asset_id_response = make_request("get", location, timeout=10, proxies=proxies, session=session)
        if asset_id_response:
            match = re.search(r'<url>http://www.roblox.com/asset/\?id=(\d+)</url>', str(asset_id_response.content))
            if match:
                return match.group(1)
    return None

def get_png_url(cookie, asset_id, proxies, session=None):
    response = make_request(
        "get",
        f'https://assetdelivery.roblox.com/v1/assetId/{asset_id}',
        cookies={".ROBLOSECURITY": cookie},
        proxies=proxies,
        timeout=10,
        session=session
    )
    if not response:
        return None
    
    data = response.json()
    if data.get("IsCopyrightProtected"):
        cprint('red', f"Copyright Protected! ID: {asset_id}")
        logging.warning(f"Copyright Protected: {asset_id}")
        return "ERROR"
    
    png_url = data.get('location')
    if png_url:
        png_response = make_request("get", png_url, timeout=15, proxies=proxies, session=session)
        if png_response:
            return png_response.content
    return None

def check_image_quality(image_bytes, min_width=585, min_height=559):
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            # Check resolution
            if img.width < min_width or img.height < min_height:
                return False, f"Image resolution too low: {img.width}x{img.height}"

            # Check for solid color.
            # getcolors(2) returns a list of colors if there are 2 or fewer, otherwise None.
            # If it returns a list of length 1, it's a solid color image.
            colors = img.convert("RGB").getcolors(2)
            if colors and len(colors) == 1:
                return False, "Image is a single solid color."

            return True, None
    except Exception as e:
        return False, f"Error checking image quality: {e}"

def download_clothing_image(cookie, clothing_id, proxies, asset_type="shirts"):
    """Download a single clothing image with optimized session reuse."""
    session = session_manager.get_session()
    
    try:
        if not os.path.exists('clothes'): os.makedirs('clothes')
        if not os.path.exists(f'clothes/{asset_type}'): os.makedirs(f'clothes/{asset_type}')

        if not clothing_id.isdigit():
            cprint('red', f"Invalid clothing ID: '{clothing_id}'")
            logging.warning(f"Invalid clothing ID: '{clothing_id}'")
            return False

        cprint('cyan', f"Processing ID: {clothing_id}...")
        
        # Try to get name with CSRF token, but continue even if it fails
        csrf_token = get_csrf_token(cookie, proxies, session)
        if csrf_token:
            item_name = get_asset_name(cookie, csrf_token, clothing_id, proxies, session)
        else:
            # Only log to file, don't show in console
            logging.warning("Failed to get CSRF token.")
            item_name = clothing_id

        safe_item_name = sanitize_filename(item_name)

        asset_id = get_asset_id(cookie, clothing_id, proxies, session)
        if not asset_id or asset_id == "ERROR":
            cprint('red', f"Failed to get asset data for ID: {clothing_id}")
            logging.error(f"Failed to get asset_id for {clothing_id}")
            return False

        png_content = get_png_url(cookie, asset_id, proxies, session)
        if not png_content or png_content == "ERROR":
            cprint('red', f"Failed to get image data for ID: {clothing_id}")
            logging.error(f"Failed to get png_content for {asset_id}")
            return False

        # Quality check before saving
        is_good, reason = check_image_quality(png_content)
        if not is_good:
            cprint('yellow', f"Discarded {clothing_id}: {reason}")
            logging.warning(f"Discarded {clothing_id} due to quality: {reason}")
            return False

        file_name = f'clothes/{asset_type}/{safe_item_name}_{"".join(random.choices(string.ascii_letters + string.digits, k=4))}.png'
        with open(file_name, 'wb') as f:
            f.write(png_content)
        
        success_message = f'Successfully downloaded {file_name}'
        cprint('green', success_message)
        logging.info(success_message)
        return True
    except Exception as e:
        error_message = f"An unexpected error occurred for ID {clothing_id}: {e}"
        cprint('red', error_message)
        logging.error(error_message)
        return False

def main():
    try:
        settings = load_settings()
        parser = argparse.ArgumentParser(
            description="Download Roblox clothing assets, with support for batch processing, retries, and proxies.",
            formatter_class=argparse.RawTextHelpFormatter
        )
        parser.add_argument('file', nargs='?', help='File path containing clothing IDs (one per line) or a single ID/URL.')
        parser.add_argument('--cookie', help='Your .ROBLOSECURITY cookie. Required for fetching private assets or names.')
        parser.add_argument('--save-cookie', action='store_true', help='Save the provided cookie to settings.json for future use.')
        parser.add_argument('--clear-settings', action='store_true', help='Clear all saved settings from settings.json.')
        parser.add_argument('--threads', type=int, default=8, help='Number of concurrent threads for batch downloading (default: 8, optimized).')
        parser.add_argument('--proxy', help='HTTP/HTTPS proxy for requests (e.g., http://user:pass@127.0.0.1:8080).')
        args = parser.parse_args()

        if args.clear_settings:
            if os.path.exists('settings.json'):
                os.remove('settings.json')
                cprint('green', "Settings cleared successfully!")
            else:
                cprint('yellow', "No settings file to clear.")
            return

        cookie = args.cookie or settings.get('cookie')
        if not cookie:
            cprint('yellow', "No .ROBLOSECURITY cookie found. The script can only download public assets and may be rate-limited.")
            cookie = input('Enter your ROBLOSECURITY cookie (leave blank to skip): ').strip()
            if cookie:
                if input('Save cookie? (y/n): ').lower() == 'y':
                    settings['cookie'] = cookie
                    save_settings(settings)
            else:
                cprint('yellow', 'Continuing without a cookie. Only public assets can be downloaded.')

        if args.save_cookie and args.cookie:
            settings['cookie'] = args.cookie
            save_settings(settings)

        proxies = {'http': args.proxy, 'https': args.proxy} if args.proxy else {}
        if args.proxy:
            cprint('cyan', f"Using proxy: {args.proxy}")

        if args.file:
            if os.path.exists(args.file):
                with open(args.file, 'r') as f:
                    ids = [line.strip() for line in f if line.strip().isdigit()]
                
                if not ids:
                    cprint('red', f"No valid numeric IDs found in {args.file}")
                    return

                cprint('cyan', f"Found {len(ids)} IDs in {args.file}.")
                if input(f"Start downloading with {args.threads} threads? (y/n): ").lower() != 'y':
                    cprint('red', "Download cancelled by user.")
                    return
                
                successful_downloads = 0
                failed_downloads = 0
                start_time = time.time()
                
                with ThreadPoolExecutor(max_workers=args.threads) as executor:
                    futures = {executor.submit(download_clothing_image, cookie, clothing_id, proxies): clothing_id for clothing_id in ids}
                    
                    for future in tqdm(as_completed(futures), total=len(futures), desc="Downloading Assets", unit="item"):
                        if future.result():
                            successful_downloads += 1
                        else:
                            failed_downloads += 1
                
                elapsed_time = time.time() - start_time
                cprint('green', f"\nBatch download complete!")
                cprint('green', f"Successful: {successful_downloads}")
                cprint('red', f"Failed: {failed_downloads}")
                cprint('cyan', f"Total time: {elapsed_time:.2f} seconds")
                cprint('cyan', f"Average time per item: {elapsed_time/len(ids):.2f} seconds")
            else:
                # Handle as a single ID or URL
                cprint('cyan', f"Attempting to download single asset: {args.file}")
                clothing_id = args.file
                if 'roblox.com/catalog/' in args.file:
                    match = re.search(r'/(\d+)/', args.file)
                    if match: clothing_id = match.group(1)
                download_clothing_image(cookie, clothing_id, proxies)
        else:
            cprint('cyan', 'Entering interactive mode. Type "exit" or "quit" to stop.')
            cprint('cyan', 'Enter a clothing ID or URL and press Enter to download.')
            while True:
                user_input = input('Enter clothing ID or URL: ').strip()
                if user_input.lower() in ['exit', 'quit']: break
                if not user_input: continue

                clothing_id = user_input
                if 'roblox.com/catalog/' in user_input:
                    match = re.search(r'/(\d+)/', user_input)
                    if match: clothing_id = match.group(1)
                    else:
                        cprint('red', 'Invalid URL.')
                        continue
                download_clothing_image(cookie, clothing_id, proxies)
                cprint('cyan', '--------------------')
        cprint('green', 'Program finished.')
    finally:
        session_manager.close()

if __name__ == "__main__":
    main()