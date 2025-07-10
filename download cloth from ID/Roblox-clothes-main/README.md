# Roblox Asset Downloader

A command-line script to download Roblox clothing assets (e.g., shirts, pants templates) using their asset IDs.
This tool can take a single asset ID or a file containing multiple IDs (one per line or as part of a URL).

## Features

- Download assets by ID.
- Batch download from a file of IDs/URLs.
- Robust error handling: Includes retries for transient network issues and checks for copyright-protected assets.
- Cookie management: Supports using a `.ROBLOSECURITY` cookie for authentication, with options to save it for future sessions.

## Basic Usage

1.  **Prerequisites**: Ensure you have Python installed, along with the libraries listed in `requirements.txt`. You can usually install them using:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the script**:

    *   To download a single asset by ID:
        ```bash
        python shyt.py <ASSET_ID>
        ```
        (Example: `python shyt.py 123456789`)

    *   To download assets from a file (e.g., `ids.txt` where each line is an ID or a full Roblox catalog URL):
        ```bash
        python shyt.py ids.txt
        ```

    *   **Cookie**: The script will prompt for your `.ROBLOSECURITY` cookie if it's the first time or if it's not saved. You can also provide it via the `--cookie` argument:
        ```bash
        python shyt.py <ASSET_ID_OR_FILE> --cookie "YOUR_COOKIE_HERE"
        ```
        Use `--save-cookie` to save the cookie provided via the command line.

    *   **Clear Settings**: To clear all saved settings including the cookie:
        ```bash
        python shyt.py --clear-settings
        ```

## Downloaded Files

Downloaded assets are saved in the `clothes/<asset_type>/` directory (e.g., `clothes/shirts/`). The default asset type is "shirts".

## Disclaimer

This tool is for educational purposes. Please respect Roblox's Terms of Service and intellectual property rights when downloading assets. Excessive use might lead to rate limiting or other actions from Roblox.
