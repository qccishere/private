from PIL import Image #line:1
import os #line:2
import glob #line:3

def remove_watermark(shirt_path, template_path, output_folder, file_index): #line:5
    try: #line:6
        original_image = Image.open(shirt_path).convert("RGBA") #line:8
        template_image = Image.open(template_path).convert("RGBA") #line:9

        if original_image.size != template_image.size: #line:12
            template_image = template_image.resize(original_image.size, Image.Resampling.LANCZOS) #line:13
            print(f"  Resized template to match shirt size ({original_image.size}) for {os.path.basename(shirt_path)}") #line:14

        combined_image = Image.alpha_composite(original_image, template_image) #line:17

        if not os.path.exists(output_folder): #line:20
            os.makedirs(output_folder) #line:21

        # --- MODIFIED LINE ---
        # Get the original filename instead of creating "z1.png", "z2.png", etc.
        output_filename = os.path.basename(shirt_path) #line:24

        output_path = os.path.join(output_folder, output_filename) #line:25
        combined_image.save(output_path, "PNG") #line:28

        print(f"Processed {os.path.basename(shirt_path)} -> {output_path}") #line:30
        return output_path #line:31
    except Exception as e: #line:32
        print(f"Error processing {shirt_path}: {e}") #line:33
        return None #line:34

def process_all_shirts(template_path="black_template.png", shirts_folder="shirts", output_folder="processed_shirts"): #line:36
    if not os.path.exists(template_path): #line:38
        print(f"Error: Template file '{template_path}' not found!") #line:39
        return #line:40

    if not os.path.exists(shirts_folder): #line:43
        os.makedirs(shirts_folder) #line:44
        print(f"Created folder '{shirts_folder}'. Please place your shirt images there.") #line:45
        print(f"Make sure you have a '{template_path}' file in the same directory as this script.") #line:46
        return #line:47

    image_paths = [] #line:50
    for extension in ['*.png', '*.jpg', '*.jpeg', '*.webp']: #line:51
        image_paths.extend(glob.glob(os.path.join(shirts_folder, extension))) #line:52

    if not image_paths: #line:54
        print(f"No image files found in '{shirts_folder}' folder.") #line:55
        print("Please add your Roblox shirt images to this folder.") #line:56
        return #line:57

    if not os.path.exists(output_folder): #line:60
        os.makedirs(output_folder) #line:61

    processed_count = 0 #line:64
    for index, image_path in enumerate(image_paths, start=1): #line:65
        processed_file = remove_watermark(image_path, template_path, output_folder, index) #line:66
        if processed_file: #line:67
            processed_count += 1 #line:68

    print(f"\nProcessing complete! {processed_count}/{len(image_paths)} shirts processed successfully.") #line:70
    # --- MODIFIED LINE ---
    print(f"Processed shirts saved with their original names to '{output_folder}' folder.") #line:71

if __name__ == "__main__": #line:73
    print("=== Roblox Shirt Watermark Remover ===") #line:74
    print("This script overlays a black template on Roblox shirts to remove watermarks") #line:75

    if not os.path.exists("black_template.png"): #line:78
        print("\nWARNING: 'black_template.png' not found!") #line:79
        print("To use this script:") #line:80
        print("1. Make sure you have a black template image named 'black_template.png'") #line:81
        print("2. Place it in the same folder as this script") #line:82
        print("3. Create a 'shirts' folder and place your Roblox shirt images there") #line:83
        print("4. Run this script again") #line:84
    else: #line:85
        process_all_shirts() #line:87