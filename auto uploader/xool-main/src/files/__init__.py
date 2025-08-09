import os
from PIL import Image
import re


def is_duplicate_file(folder_path, filename):
    pattern = re.compile(r"^(.*?)(_\d+)?(\.[^.]*)?$")
    match = pattern.match(filename)

    if not match:
        return False

    base_name = match.group(1) + (match.group(3) or "")
    for existing_file in os.listdir(folder_path):
        existing_match = pattern.match(existing_file)
        existing_base_name = existing_match.group(1) + (existing_match.group(3) or "")
        if base_name == existing_base_name and existing_file != filename:
            return True
    return False


def remove_png():
    for root, dirs, files in os.walk("src/assets"):
        if 'template' in root:
            continue

        for file in files:
            if file.endswith('.png'):
                file_path = os.path.join(root, file)
                
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")
                    

def is_similar(new_image_path, folder_path, threshold=1):
    try:
        import imagehash
    except Exception as e:
        print(f"imagehash not available ({e}); skipping similarity check.")
        return False
    folder_path = {"classicshirts": "src/assets/shirts", "classicpants": "src/assets/pants"}[folder_path]
    with Image.open(new_image_path) as new_img:
        new_image_hash = imagehash.phash(new_img)
    new_image_name = os.path.basename(new_image_path)
    for filename in os.listdir(folder_path):
        image_path = os.path.join(folder_path, filename)
        if filename == new_image_name:
            continue
        if os.path.isfile(image_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            with Image.open(image_path) as folder_img:
                folder_image_hash = imagehash.phash(folder_img)
            if new_image_hash - folder_image_hash < threshold:
                print(f"{new_image_name} duped by {filename}")
                return True
    return False
