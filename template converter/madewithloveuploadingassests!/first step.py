from selenium import webdriver #line:1
from selenium .webdriver .common .by import By #line:2
from selenium .webdriver .support .ui import WebDriverWait #line:3
from selenium .webdriver .support import expected_conditions as EC #line:4
from selenium .common .exceptions import TimeoutException ,NoSuchElementException ,WebDriverException #line:5
import time #line:6
import re #line:7
import os #line:8
import urllib .parse #line:9

def setup_driver():#line:22
    """Setup Chrome driver with optimized performance settings."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in background for better performance
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')  # Don't load images for faster loading
    options.add_argument('--disable-javascript')  # Disable JS if not needed
    options.add_argument('--window-size=1280,720')
    
    # Performance optimizations
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # Block images
        "profile.default_content_settings.popups": 0,  # Block popups
        "profile.managed_default_content_settings.media_stream": 2,  # Block media
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)  # Reduced from default
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        print("Make sure ChromeDriver is installed and in PATH")
        return None

def extract_ids_from_page(O0OO0O0O0OO0O000O):#line:52
    """Extract IDs from the current page with optimized element finding."""
    OO00000O0OO0OO0O0 =[] #line:53
    try:#line:54
        # Use more specific and faster selectors
        O00000OO00000O000 = WebDriverWait(O0OO0O0O0OO0O000O, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/catalog/']"))
        ) #line:55
        
        for O00OO0O0000OO0O00 in O00000OO00000O000:#line:60
            try:#line:61
                O0O0O0OO0O0O00OOO =O00OO0O0000OO0O00 .get_attribute ("href")#line:62
                if O0O0O0OO0O0O00OOO:#line:63
                    # Optimized regex pattern
                    OO0OO000000O0O0OO =re .search (r'/catalog/(\d+)/',O0O0O0OO0O0O00OOO )#line:64
                    if OO0OO000000O0O0OO:#line:65
                        O0OO00OO0OO0000O0 =OO0OO000000O0O0OO .group (1 )#line:66
                        if O0OO00OO0OO0000O0 not in OO00000O0OO0OO0O0:#line:67
                            OO00000O0OO0OO0O0 .append (O0OO00OO0OO0000O0 )#line:68
            except Exception as e:#line:69
                print(f"Error processing link: {e}")
                continue #line:70
    except TimeoutException:#line:71
        print("Timeout waiting for catalog links")#line:72
    except Exception as O0O0OO0OO0000000O:#line:73
        print (f"Error finding elements: {O0O0OO0OO0000000O}")#line:74
    return OO00000O0OO0OO0O0 #line:75

def main():#line:76
    """Main function with improved error handling and performance."""
    driver = setup_driver()
    if not driver:
        return
        
    try:
        print("Starting ID extraction...")
        start_time = time.time()
        
        # Navigate to the catalog page
        base_url = "https://www.roblox.com/catalog/?Category=1&Subcategory=1&SortType=0&SortAggregation=AllTime&CreatorName=&CreatorType=User&GenreFilter=1"
        driver.get(base_url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/catalog/']"))
        )
        
        all_ids = set()  # Use set to avoid duplicates automatically
        max_pages = 10  # Configurable limit
        current_page = 1
        
        while current_page <= max_pages:
            print(f"Processing page {current_page}...")
            
            # Extract IDs from current page
            page_ids = extract_ids_from_page(driver)
            if not page_ids:
                print(f"No IDs found on page {current_page}, stopping.")
                break
                
            all_ids.update(page_ids)
            print(f"Found {len(page_ids)} IDs on page {current_page} (Total unique: {len(all_ids)})")
            
            # Try to go to next page
            try:
                # Look for next page button with more specific selector
                next_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Next']"))
                )
                
                # Scroll to button if needed
                driver.execute_script("arguments[0].scrollIntoView();", next_button)
                time.sleep(1)  # Brief pause for scroll
                
                next_button.click()
                current_page += 1
                
                # Wait for new page to load
                time.sleep(2)
                
            except (TimeoutException, NoSuchElementException):
                print("No more pages or next button not found.")
                break
            except Exception as e:
                print(f"Error navigating to next page: {e}")
                break
        
        # Save results
        if all_ids:
            output_file = "output.txt"
            with open(output_file, 'w') as f:
                for asset_id in sorted(all_ids):  # Sort for consistency
                    f.write(f"{asset_id}\n")
            
            elapsed_time = time.time() - start_time
            print(f"\nExtraction complete!")
            print(f"Total unique IDs extracted: {len(all_ids)}")
            print(f"Saved to: {output_file}")
            print(f"Time taken: {elapsed_time:.2f} seconds")
            print(f"Average time per page: {elapsed_time/current_page:.2f} seconds")
        else:
            print("No IDs were extracted.")
            
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if driver:
            driver.quit()
            print("Browser closed.")

if __name__ == "__main__":
    main()