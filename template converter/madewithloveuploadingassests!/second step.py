import requests
import os
import time
import xml.etree.ElementTree as ET
import re # Import regex module
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

def get_asset_url(asset_id):
    """Fetches the asset delivery information and extracts the final content URL using a multi-step process."""
    step1_url = f"https://assetdelivery.roblox.com/v1/assetId/{asset_id}"
    session = requests.Session() # Use a session for potential cookie handling/efficiency
    session.headers.update({'User-Agent': 'Mozilla/5.0'}) # Add a user-agent

    try:
        # --- Step 1: Get initial location URL ---
        print(f"  [Step 1] Fetching initial info for {asset_id}...")
        response1 = session.get(step1_url, timeout=15, allow_redirects=True)
        response1.raise_for_status()

        try:
            data1 = response1.json()
            location1 = data1.get('location')
            if not location1:
                print(f"  [Step 1] Error: 'location' key not found in JSON response for {asset_id}. Response: {data1}")
                return None
            print(f"  [Step 1] Intermediate URL found: {location1}")
        except requests.exceptions.JSONDecodeError:
            print(f"  [Step 1] Error: Failed to decode JSON from {step1_url}. Content: {response1.text[:200]}...") # Log part of the content
             # Fallback: Check if the response *is* the XML (sometimes happens for older assets?)
            print(f"  [Step 1] Assuming XML response might contain final URL directly...")
            try:
                 root = ET.fromstring(response1.content)
                 for elem in root.iter():
                     if elem.text and ('rbxcdn.com' in elem.text or 'roblox.com/asset' in elem.text) and elem.text.strip().startswith('http'):
                          final_url = elem.text.strip()
                          print(f"  [Fallback] Found potential final URL in initial response: {final_url}")
                          return final_url
                 print(f"  [Fallback] Could not find URL in XML structure for {asset_id}")
                 return None
            except ET.ParseError:
                 print(f"  [Fallback] Content was not valid XML either for {asset_id}.")
                 return None

        # --- Step 2: Fetch intermediate URL to get XML with real asset ID ---
        print(f"  [Step 2] Fetching intermediate URL: {location1}...")
        response2 = session.get(location1, timeout=15, allow_redirects=True)
        response2.raise_for_status()

        # Check content type - should ideally be XML now
        if 'xml' not in response2.headers.get('Content-Type', '').lower():
             # Sometimes the intermediate URL *itself* points directly to the final image
             if 'image' in response2.headers.get('Content-Type', '').lower():
                 print(f"  [Step 2 Warning] Intermediate URL pointed directly to an image ({response2.headers.get('Content-Type')}). Using this URL: {location1}")
                 return location1
             else:
                print(f"  [Step 2 Warning] Unexpected content type ({response2.headers.get('Content-Type')}) from {location1}. Trying to parse as XML anyway.")
                # Continue trying to parse as XML, it might still work

        try:
            xml_content = response2.content
            # Decode XML content explicitly, trying common encodings
            try:
                decoded_xml = xml_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    decoded_xml = xml_content.decode('iso-8859-1')
                except UnicodeDecodeError:
                    print(f"  [Step 2] Error: Could not decode XML content for {asset_id}.")
                    return None # Give up if decoding fails

            # Use regex to find the specific URL format, as parsing might fail on malformed XML
            match = re.search(r'<url>.*http://www\.roblox\.com/asset/\?id=(\d+).*</url>', decoded_xml, re.IGNORECASE)
            if not match:
                 # Fallback to iterating elements if regex fails
                 print(f"  [Step 2 Warning] Could not find regex pattern '<url>http://www.roblox.com/asset/?id=...</url>'. Trying general XML parse...")
                 root = ET.fromstring(xml_content) # Parse the original bytes
                 real_asset_id = None
                 for elem in root.iter('url'): # Look specifically for 'url' tags
                      if elem.text and 'roblox.com/asset/?id=' in elem.text:
                           try:
                                real_asset_id = elem.text.split('id=')[-1]
                                if real_asset_id.isdigit():
                                     print(f"  [Step 2] Found real asset ID via XML parse: {real_asset_id}")
                                     break # Found it
                                else: real_asset_id = None # Reset if not digits
                           except Exception:
                                real_asset_id = None # Ignore errors parsing this specific tag
                 if not real_asset_id:
                     print(f"  [Step 2] Error: Could not extract real asset ID from XML content for {asset_id}. XML: {decoded_xml[:200]}...")
                     return None
            else:
                 real_asset_id = match.group(1)
                 print(f"  [Step 2] Found real asset ID via regex: {real_asset_id}")

        except ET.ParseError as e:
            print(f"  [Step 2] Error: Failed to parse XML from {location1}: {e}. Content: {response2.text[:200]}...")
            return None
        except Exception as e: # Catch other potential errors during regex/parsing
            print(f"  [Step 2] Unexpected error during XML processing for {asset_id}: {e}")
            return None

        # --- Step 3: Fetch final asset delivery info using the real asset ID ---
        step3_url = f"https://assetdelivery.roblox.com/v1/assetId/{real_asset_id}"
        print(f"  [Step 3] Fetching final info using real ID {real_asset_id}...")
        response3 = session.get(step3_url, timeout=15, allow_redirects=True)
        response3.raise_for_status()

        try:
            data3 = response3.json()
            final_location = data3.get('location')
            if not final_location:
                print(f"  [Step 3] Error: 'location' key not found in final JSON response for real ID {real_asset_id}.")
                return None
            print(f"  [Step 3] Final CDN URL found: {final_location}")
            return final_location # Success!
        except requests.exceptions.JSONDecodeError:
            # If the final step doesn't give JSON, maybe *it* contains the image? Unlikely but check.
             if 'image' in response3.headers.get('Content-Type', '').lower():
                 print(f"  [Step 3 Warning] Final URL pointed directly to an image ({response3.headers.get('Content-Type')}). Using this URL: {step3_url}")
                 # This is less likely, usually the JSON location is the image, but as a fallback...
                 return step3_url # Return the URL we queried, hoping it's the image
             else:
                print(f"  [Step 3] Error: Failed to decode final JSON from {step3_url} for real ID {real_asset_id}. Content: {response3.text[:200]}...")
                return None

    except requests.exceptions.Timeout:
        print(f"Error: Request timed out for ID {asset_id}.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP Error {e.response.status_code} for ID {asset_id} at URL: {e.request.url}")
        # Log specific common errors
        if e.response.status_code == 400:
             print("  (This might indicate an invalid or content-deleted asset ID)")
        elif e.response.status_code == 403:
             print("  (This might indicate the asset is not approved or is off-sale)")
        elif e.response.status_code == 429:
             print("  (Rate limited! Consider increasing the delay between requests)")
        elif e.response.status_code == 500:
             print("  (Roblox server error)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network request failed for ID {asset_id}: {e}")
        return None
    except Exception as e: # Catch any other unexpected errors
        import traceback
        print(f"Error: An unexpected error occurred processing ID {asset_id}: {e}")
        print(traceback.format_exc()) # Print stack trace for debugging
        return None

def download_asset(asset_id, download_folder="downloaded_assets"):
    """Downloads the asset image using its ID."""
    content_url = get_asset_url(asset_id)
    if not content_url:
        print(f"Skipping download for ID {asset_id} due to previous error.")
        return False

    print(f"Found content URL for {asset_id}: {content_url}")

    try:
        image_response = requests.get(content_url, timeout=30) # Longer timeout for download
        image_response.raise_for_status()

        # Ensure the download folder exists
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)
            print(f"Created directory: {download_folder}")

        # Determine file extension (attempt to guess, default to png)
        content_type = image_response.headers.get('Content-Type', 'image/png').lower()
        extension = ".png" # Default
        if 'jpeg' in content_type or 'jpg' in content_type:
            extension = ".jpg"
        elif 'gif' in content_type:
            extension = ".gif"
        elif 'webp' in content_type:
            extension = ".webp"
        # Add more types if needed

        file_path = os.path.join(download_folder, f"{asset_id}{extension}")

        with open(file_path, 'wb') as f:
            f.write(image_response.content)
        print(f"Successfully downloaded {asset_id} to {file_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image for ID {asset_id} from {content_url}: {e}")
        return False
    except IOError as e:
        print(f"Error saving file for ID {asset_id}: {e}")
        return False

class RateLimiter:
    """Simple rate limiter that adapts to rate limit responses."""
    def __init__(self, initial_delay=0.1):
        self.delay = initial_delay
        self.last_request_time = 0
        
    def wait(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        self.last_request_time = time.time()
    
    def handle_rate_limit(self):
        """Increase delay when rate limited."""
        self.delay = min(self.delay * 2, 5.0)  # Max 5 seconds
        print(f"Rate limited! Increasing delay to {self.delay:.2f}s")
    
    def reset(self):
        """Reset delay on successful requests."""
        if self.delay > 0.1:
            self.delay = max(self.delay * 0.9, 0.1)  # Gradually decrease

def main(ids_file="output.txt", download_folder="downloaded_assets", max_workers=5):
    """Main function to read IDs and initiate downloads with parallel processing."""
    if not os.path.exists(ids_file):
        print(f"Error: IDs file '{ids_file}' not found.")
        return

    with open(ids_file, 'r') as f:
        asset_ids = [line.strip() for line in f if line.strip().isdigit()]

    print(f"Found {len(asset_ids)} IDs in {ids_file}.")
    print(f"Starting parallel downloads with {max_workers} workers...")

    successful_downloads = 0
    failed_downloads = 0
    
    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_id = {
            executor.submit(download_asset, asset_id, download_folder): asset_id 
            for asset_id in asset_ids
        }
        
        # Process completed downloads with progress bar
        for future in tqdm(as_completed(future_to_id), total=len(asset_ids), desc="Downloading Assets", unit="asset"):
            asset_id = future_to_id[future]
            try:
                result = future.result()
                if result:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as e:
                print(f"Exception occurred for asset {asset_id}: {e}")
                failed_downloads += 1

    print("\n--- Download Summary ---")
    print(f"Successful: {successful_downloads}")
    print(f"Failed:     {failed_downloads}")
    print("------------------------")

if __name__ == "__main__":
    main() 