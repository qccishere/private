from selenium import webdriver #line:1
from selenium .webdriver .common .by import By #line:2
from selenium .webdriver .support .ui import WebDriverWait #line:3
from selenium .webdriver .support import expected_conditions as EC #line:4
from selenium .common .exceptions import TimeoutException ,NoSuchElementException ,WebDriverException #line:5
import time #line:6
import re #line:7
import os #line:8
import urllib .parse #line:9
OUTPUT_FILENAME ="output.txt"#line:12
WAIT_TIMEOUT =15 #line:13
SCROLL_PAUSE_TIME =4 #line:14
MAX_PAGES_TO_CHECK =20 #line:15
LINK_ID_PATTERN =re .compile (r'/catalog/(\d+)/')#line:18
def setup_driver ():#line:22
    ""#line:23
    O0O0OOOOO00000O0O =None #line:24
    try :#line:25
        OOO0OO0OOO0O0O0OO =webdriver .ChromeOptions ()#line:27
        OOO0OO0OOO0O0O0OO .add_argument ("--disable-gpu")#line:29
        OOO0OO0OOO0O0O0OO .add_argument ("--no-sandbox")#line:30
        OOO0OO0OOO0O0O0OO .add_argument ('--disable-dev-shm-usage')#line:31
        OOO0OO0OOO0O0O0OO .add_argument ("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")#line:32
        O0O0OOOOO00000O0O =webdriver .Chrome (options =OOO0OO0OOO0O0O0OO )#line:33
        print ("Using Chrome WebDriver.")#line:34
    except WebDriverException as OOOOOOO0O0O0O0OOO :#line:35
        print (f"Chrome WebDriver setup failed: {OOOOOOO0O0O0O0OOO}")#line:36
        try :#line:37
            OO0OOOO0000O0O000 =webdriver .FirefoxOptions ()#line:39
            O0O0OOOOO00000O0O =webdriver .Firefox (options =OO0OOOO0000O0O000 )#line:41
            print ("Using Firefox WebDriver (GeckoDriver).")#line:42
        except WebDriverException as OO0O00O00O0OO0OOO :#line:43
            print (f"Firefox WebDriver setup failed: {OO0O00O00O0OO0OOO}")#line:44
            print ("Error: Please ensure you have the correct WebDriver (chromedriver or geckodriver) installed and accessible.")#line:45
            O0O0OOOOO00000O0O =None #line:46
    if O0O0OOOOO00000O0O :#line:48
        O0O0OOOOO00000O0O .set_page_load_timeout (30 )#line:49
    return O0O0OOOOO00000O0O #line:50
def extract_ids_from_page (O0OO0O0O0OO0O000O ):#line:52
    ""#line:53
    O0O0OOOO0OOOO0O00 =set ()#line:54
    try :#line:55
        O0OO00O00OO0000OO =WebDriverWait (O0OO0O0O0OO0O000O ,WAIT_TIMEOUT )#line:56
        OO00O0O00O00OOO0O =O0OO00O00OO0000OO .until (EC .presence_of_all_elements_located ((By .CSS_SELECTOR ,"a[href*='/catalog/']")))#line:58
        for O0000000O000O00OO in OO00O0O00O00OOO0O :#line:61
            O0OOOOOOO0O0O0000 =O0000000O000O00OO .get_attribute ('href')#line:62
            if O0OOOOOOO0O0O0000 :#line:63
                O00O00O000OOOOO00 =LINK_ID_PATTERN .search (O0OOOOOOO0O0O0000 )#line:64
                if O00O00O000OOOOO00 :#line:65
                    O0O0OOOO0OOOO0O00 .add (O00O00O000OOOOO00 .group (1 ))#line:66
    except TimeoutException :#line:68
        print ("Info: Did not find any item links within the wait time (TimeoutException).")#line:70
    except NoSuchElementException :#line:71
        print ("Error: Could not find the specified elements (item links). Page structure might have changed.")#line:72
    except Exception as O00OO00O00000OO00 :#line:73
        print (f"An unexpected error occurred during ID extraction: {O00OO00O00000OO00}")#line:74
    return O0O0OOOO0OOOO0O00 #line:76
if __name__ =="__main__":#line:79
    print ("=== Selenium Roblox ID Scraper ===")#line:80
    input_url =input ("Enter the FULL URL of the Roblox Catalog Search or Group Store page: ").strip ()#line:82
    if input_url .startswith ("www."):#line:85
        input_url ="https://"+input_url #line:86
        print (f"Prepended https://. Using URL: {input_url}")#line:87
    if not input_url .startswith ("http"):#line:89
        print ("Invalid URL. Please provide the full URL starting with http:// or https:// (or www.)")#line:90
        exit ()#line:91
    target_url =input_url #line:94
    print (f"Target URL: {target_url}")#line:95
    driver =setup_driver ()#line:98
    if not driver :#line:99
        exit ()#line:100
    all_extracted_ids =set ()#line:102
    try :#line:103
        print (f"Navigating to: {target_url}")#line:104
        driver .get (target_url )#line:105
        print (f"Waiting up to {WAIT_TIMEOUT} seconds for page elements to load...")#line:108
        try :#line:109
            WebDriverWait (driver ,WAIT_TIMEOUT ).until (EC .presence_of_element_located ((By .CSS_SELECTOR ,".items-list, .item-cards-container, ul.item-list, body")))#line:113
            print ("Initial page elements loaded.")#line:114
        except TimeoutException :#line:115
            print (f"Warning: Timed out waiting for initial page elements. Proceeding anyway.")#line:116
        page_num =1 #line:119
        max_pages =MAX_PAGES_TO_CHECK #line:120
        while page_num <=max_pages :#line:122
            print (f"\n--- Processing Page {page_num} ---")#line:123
            time .sleep (1.5 )#line:125
            current_ids =extract_ids_from_page (driver )#line:128
            if not current_ids and page_num ==1 :#line:129
                print ("Warning: No IDs found on the first page. Check URL and page content.")#line:130
            newly_found_count =len (current_ids .difference (all_extracted_ids ))#line:134
            print (f"Found {len(current_ids)} unique IDs in current view. ({newly_found_count} new this page)")#line:135
            all_extracted_ids .update (current_ids )#line:136
            try :#line:139
                next_button_selector =(".pagination-container .pager-next > a, " ".pagination .pager-next > a, " ".pagination-container button.page-next, " ".pagination button.page-next, " "button[aria-label='Next Page']")#line:147
                next_button =WebDriverWait (driver ,5 ).until (EC .element_to_be_clickable ((By .CSS_SELECTOR ,next_button_selector )))#line:151
                print ("Next Page button found and clickable. Clicking...")#line:153
                try :#line:154
                    next_button .click ()#line:155
                except Exception as click_error :#line:156
                    print (f"Standard click failed ({click_error}), trying JavaScript click...")#line:157
                    driver .execute_script ("arguments[0].click();",next_button )#line:158
                page_num +=1 #line:160
                print (f"Waiting {SCROLL_PAUSE_TIME} seconds for page {page_num} to load...")#line:162
                time .sleep (SCROLL_PAUSE_TIME )#line:163
            except TimeoutException :#line:165
                print ("Next Page button not found or not clickable after 5 seconds. Assuming last page.")#line:166
                break #line:167
            except Exception as e :#line:168
                 print (f"An error occurred trying to find/click Next Page: {e}")#line:169
                 break #line:170
            if page_num >max_pages :#line:172
                 print (f"Reached maximum page limit ({max_pages}).")#line:173
                 break #line:174
    except WebDriverException as e :#line:176
        print (f"A WebDriver error occurred: {e}")#line:177
    except Exception as e :#line:178
        print (f"An unexpected error occurred during scraping: {e}")#line:179
    finally :#line:180
        if driver :#line:181
            print ("Closing browser...")#line:182
            driver .quit ()#line:183
    if all_extracted_ids :#line:186
        print (f"\nFinished scraping. Found a total of {len(all_extracted_ids)} unique asset IDs.")#line:187
        try :#line:190
            sorted_ids =sorted (list (all_extracted_ids ),key =int )#line:191
            with open (OUTPUT_FILENAME ,'w')as file :#line:192
                for item_id in sorted_ids :#line:193
                    file .write (f"{item_id}\n")#line:194
            print (f"Successfully wrote {len(sorted_ids)} IDs to {OUTPUT_FILENAME}")#line:195
        except IOError as e :#line:196
            print (f"Error writing ID list to file {OUTPUT_FILENAME}: {e}")#line:197
    else :#line:199
        print ("\nNo asset IDs were found during scraping.")#line:200
    print ("\nScript finished.")