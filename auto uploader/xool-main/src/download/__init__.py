import requests, random, os

from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Reuse a pooled session for better performance and reliability
_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)
_DEFAULT_TIMEOUT = 30


def get_asset_id(cookie, clothing_id):
    try:
        response = _session.get(
            f'https://assetdelivery.roblox.com/v1/assetId/{clothing_id}',
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=_DEFAULT_TIMEOUT
        )
        response.raise_for_status() 
        data = response.json()
        if data.get("IsCopyrightProtected"):
            print(f"Copyright Protected! ID: {clothing_id}")
            return None
        location = data.get('location')
        if location:
            asset_id_response = _session.get(location, timeout=_DEFAULT_TIMEOUT)
            asset_id_response.raise_for_status()
            asset_id_content = str(asset_id_response.content)
            asset_id = asset_id_content.split('<url>http://www.roblox.com/asset/?id=')[1].split('</url>')[0]
            return asset_id
        else:
            return None
    except requests.RequestException as e:
        print(f"Error: {e}")
        return None


def get_png_url(cookie, asset_id):
    try:
        response = _session.get(
            f'https://assetdelivery.roblox.com/v1/assetId/{asset_id}',
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=_DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        if data.get("IsCopyrightProtected"):
            print(f"Copyright Protected! ID: {asset_id}")
            return None
        png_url = data.get('location')
        return _session.get(png_url, timeout=_DEFAULT_TIMEOUT).content
    except requests.RequestException as e:
        print(f"Error: {e}")
        return None


def replace_template(path):
    img1 = Image.open(path)
    img2 = Image.open("src/assets/template/template.png")
    img1.paste(img2, (0,0), mask = img2)
    img1.save(path.replace("temp", ""))
    os.remove(path)


def save_asset(cookie, clothing_id, asset_type, asset_name, max_score, path_2):
 try:
    path = f"{path_2}/src/assets/temp/{asset_type}/{asset_name}_{random.randint(0, 100)}.png"
    with open(path, "wb") as f:
        f.write(get_thumbnail(clothing_id))
    # Lazy-load NSFW checker to avoid heavy import unless needed
    if max_score is not None:
        try:
            import opennsfw2 as n2
            if n2.predict_image(path) > max_score:
                os.remove(path)
                print("asset failed to pass nudity check")
                print(clothing_id)
                return False
        except Exception as e:
            # If NSFW model not available, proceed without blocking
            print(f"NSFW check unavailable or failed: {e}. Proceeding...")
    os.remove(path)
    asset_id = get_asset_id(cookie, clothing_id)
    if not asset_id:
        print("Failled to scrape asset item id")
        return False
    png = get_png_url(cookie, asset_id)
    if not png:
        print("Failed to download asset png")
        return False
    path = f"{path_2}/src/assets/temp/{asset_type}/{asset_name}_{random.randint(0, 100)}.png"
    with open(path, 'wb') as f:
        f.write(png)
    replace_template(path)
    print("downloaded one asset")
    return path.replace("temp", "")
 except Exception as e:
    print(f"ERROR: {e}")
    try:
        os.remove(path)
    except:
        pass
    return False


def get_thumbnail(asset_id):
    thumb_batch_resp = _session.post(
        "https://thumbnails.roblox.com/v1/batch",
        json=[{"format": "png", "requestId": f"{asset_id}::Asset:420x420:png:regular", "size": "420x420", "targetId": asset_id, "token": "", "type": "Asset"}],
        timeout=_DEFAULT_TIMEOUT
    ).json()
    return _session.get(thumb_batch_resp["data"][0]["imageUrl"], timeout=_DEFAULT_TIMEOUT).content
