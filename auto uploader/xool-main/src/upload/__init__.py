import requests, json, time, uuid
from requests_toolbelt.multipart.encoder import MultipartEncoder
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Reuse a pooled session to improve throughput and reliability
_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)
_DEFAULT_TIMEOUT = 30


def create_asset(name, path, asset_type, cookie, group_id, description, _total_tries, wait_time):
    payload = {
        "assetType": asset_type,
        "creationContext": {
            "creator": {
                "groupId": group_id
            },
            "expectedPrice": 10
        },  
        "description": description,
        "displayName": name,
    }
    # Ensure file handle is closed promptly
    with open(f'{path}', 'rb') as file_handle:
        multipart_data = MultipartEncoder(
            fields={
                'request': json.dumps(payload),
                'fileContent': ('test.png', file_handle, 'image/png')
            }
        )
        headers = {'X-CSRF-TOKEN': cookie.x_token()}
        headers['Content-Type'] = multipart_data.content_type
        dd = _session.post(
            "https://apis.roblox.com/assets/user-auth/v1/assets",
            data=multipart_data,
            headers=headers,
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=_DEFAULT_TIMEOUT
        ).json()
    if not dd.get("operationId"):
        print(dd.get("message", "Unknown error"))
        if "InsufficientFunds" in dd.get("message", ""):
            return 2
        elif "unauthorized" in dd.get("message", ""):
            return 3
        return False
    total_tries = 0
    while total_tries < _total_tries:
        data = _session.get(
            f"https://apis.roblox.com/assets/user-auth/v1/operations/{dd['operationId']}",
            headers={'X-CSRF-TOKEN': cookie.x_token()},
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=_DEFAULT_TIMEOUT
        )
        if data.status_code == 200 and data.json().get("done") not in [None, False]:
            return data.json()
        else:
            total_tries += 1
            time.sleep(wait_time)


def release_asset(cookie, asset_id, price, name, description, group_id):
    headers = {
        "X-CSRF-TOKEN": cookie.x_token(),
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={cookie.cookie};"
    }
    data = {    
        "saleLocationConfiguration": {"saleLocationType": 1, "places": []},
        "targetId": asset_id,
        "priceInRobux": price,
        "publishingType": 2,
        "idempotencyToken": str(uuid.uuid4()),
        "publisherUserId": cookie.user_id,
        "creatorGroupId": group_id,
        "name": name,
        "description": description,
        "isFree": False,
        "agreedPublishingFee": 0,
        "priceOffset": 0,
        "quantity": 0,
        "quantityLimitPerUser": 0,
        "resaleRestriction": 2,
        "targetType": 0
    }
    return _session.post(
        f"https://itemconfiguration.roblox.com/v1/collectibles",
        headers=headers,
        json=data,
        timeout=_DEFAULT_TIMEOUT
    )
    
