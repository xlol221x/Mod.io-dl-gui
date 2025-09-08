import re
import os
import asyncio
import json
import zipfile
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
from playwright.async_api import async_playwright
import threading
import queue

# ----------------------
# CONFIGURATION
# ----------------------
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloaded")
OAUTH_KEY_FILE = "oauth_key.txt"

# Create a queue to handle messages between threads
message_queue = queue.Queue()

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def get_oauth_key(root):
    """
    Loads the OAuth key from a file or prompts the user to enter and save it.
    """
    try:
        with open(OAUTH_KEY_FILE, "r") as f:
            oauth_key = f.read().strip()
            if oauth_key:
                return oauth_key
    except FileNotFoundError:
        pass # File not found, proceed to ask user

    # If the key is not found or is empty, ask the user to enter it
    oauth_key = simpledialog.askstring("OAuth Key Required", "Please enter your mod.io OAuth key:", parent=root)
    if oauth_key:
        try:
            with open(OAUTH_KEY_FILE, "w") as f:
                f.write(oauth_key)
            messagebox.showinfo("Key Saved", f"OAuth key successfully saved to '{OAUTH_KEY_FILE}'.")
            return oauth_key
        except Exception as e:
            messagebox.showerror("File Error", f"An error occurred while saving the key: {e}")
            return None
    else:
        return None

def parse_mod_url(url):
    """
    Extract game ID and mod ID from a mod.io URL
    Handles both 'games' and 'g' formats, with numerical IDs or text slugs.
    Example: https://mod.io/games/12345/mods/67890
    Example: https://mod.io/g/drg/m/new-passive-perk-slot
    """
    # Regex for numerical IDs
    match_num = re.search(r'/games/(\d+)/mods/(\d+)', url)
    if match_num:
        return match_num.group(1), match_num.group(2)
    
    # Regex for slug-based IDs
    match_slug = re.search(r'/g/([^/]+)/m/([^/]+)', url)
    if match_slug:
        return match_slug.group(1), match_slug.group(2)

    return None, None

def unzip_pak_file(zip_filepath, extract_to_folder, message_queue):
    """
    Unzips a .zip file, extracts the first .pak file found, and deletes the original zip.
    """
    pak_found = False
    try:
        message_queue.put((f"Found .pak file. Extracting from '{os.path.basename(zip_filepath)}'...\n", "normal"))
        with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
            for file_in_zip in zip_ref.namelist():
                if file_in_zip.endswith('.pak'):
                    zip_ref.extract(file_in_zip, extract_to_folder)
                    pak_found = True
                    message_queue.put(("Extraction complete.\n", "normal"))
                    break
        
    except zipfile.BadZipFile:
        message_queue.put(("Error: The downloaded file is not a valid zip archive. Skipping unzip.\n", "red"))
        return
    except Exception as e:
        message_queue.put((f"An error occurred during unzip: {e}\n", "red"))
        return

    # Only attempt to delete if a .pak file was found and extraction was successful
    if pak_found:
        message_queue.put(("Cleaning up...\n", "normal"))
        try:
            os.remove(zip_filepath)
            message_queue.put((f"Original zip file deleted: {zip_filepath}\n", "normal"))
        except Exception as e:
            message_queue.put((f"An error occurred during cleanup: {e}\n", "red"))

async def fetch_api_data(page, url, auth_key, message_queue):
    """
    Helper function to make an API call using page.evaluate() and handle errors.
    Returns the JSON data as a Python dictionary.
    """
    response_text = await page.evaluate('''async (params) => {
        const { url, authKey } = params;
        const headers = new Headers();
        headers.append("Authorization", `Bearer ${authKey}`);
        headers.append("Accept", "application/json");

        const response = await fetch(url, { headers: headers });
        if (!response.ok) {
            throw new Error(`Failed to fetch API info. Status code: ${response.status}.`);
        }
        return await response.text();
    }''', {'url': url, 'authKey': auth_key})
    return json.loads(response_text)

async def download_mod(game_identifier, mod_identifier, oauth_key, message_queue):
    """
    Fetches the mod file information from the mod.io API and downloads the file
    by leveraging a full browser session to bypass Cloudflare. Handles both
    numerical and text-based game/mod identifiers.
    """
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    try:
        async with async_playwright() as p:
            # Launch a browser instance
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            message_queue.put(("Bypassing Cloudflare challenge...\n", "normal"))
            # Set OAuth header for future requests within this context
            await context.set_extra_http_headers({
                "Authorization": f"Bearer {oauth_key}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })

            # First, navigate to the mod.io homepage to complete the Cloudflare challenge.
            await page.goto("https://mod.io", wait_until="networkidle")
            message_queue.put(("Cloudflare challenge bypassed.\n", "normal"))

            # Determine if the identifiers are numerical or slugs
            is_game_id_num = game_identifier.isdigit()
            is_mod_id_num = mod_identifier.isdigit()
            
            # If identifiers are slugs, we need to look up their numerical IDs
            if not is_game_id_num or not is_mod_id_num:
                message_queue.put(("Identifiers are slugs. Looking up numerical IDs...\n", "normal"))
                # Fetch game ID
                game_api_url = f"https://api.mod.io/v1/games?name_id={game_identifier}"
                game_data = await fetch_api_data(page, game_api_url, oauth_key, message_queue)
                if not game_data["data"]:
                    raise Exception(f"Game '{game_identifier}' not found on mod.io.")
                game_id = str(game_data["data"][0]["id"])

                # Fetch mod ID
                mod_api_url = f"https://api.mod.io/v1/games/{game_id}/mods?name_id={mod_identifier}"
                mod_data = await fetch_api_data(page, mod_api_url, oauth_key, message_queue)
                if not mod_data["data"]:
                    raise Exception(f"Mod '{mod_identifier}' not found for game '{game_identifier}'.")
                mod_id = str(mod_data["data"][0]["id"])
            else:
                # Use the provided numerical IDs directly
                game_id = game_identifier
                mod_id = mod_identifier
                
            # Now, use the numerical IDs to fetch the mod files
            api_url = f"https://api.mod.io/v1/games/{game_id}/mods/{mod_id}/files"
            message_queue.put((f"Fetching mod information from API: {api_url}\n", "normal"))
            
            data = await fetch_api_data(page, api_url, oauth_key, message_queue)
            
            if "data" in data and len(data["data"]) > 0:
                file_info = data["data"][0]
                download_url = file_info["download"]["binary_url"]
                filename = file_info["filename"]
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                
                message_queue.put((f"Found mod file: {filename}. Downloading from {download_url}...\n", "normal"))
                
                # Use page.evaluate to make the fetch call for the binary download
                binary_data_base64 = await page.evaluate(r'''async (url) => {
                    const response = await fetch(url);
                    if (!response.ok) {
                        throw new Error(`Failed to download file. Status code: ${response.status}.`);
                    }
                    const buffer = await response.arrayBuffer();
                    // Convert ArrayBuffer to base64 string for transfer back to Python
                    const base64String = btoa(String.fromCharCode(...new Uint8Array(buffer)));
                    return base64String;
                }''', download_url)

                # Convert base64 string back to bytes in Python
                import base64
                binary_data = base64.b64decode(binary_data_base64)

                with open(filepath, "wb") as f:
                    f.write(binary_data)
                
                message_queue.put((f"Download complete: {filepath}\n", "normal"))

                # Check if the downloaded file is a zip and unzip it
                if zipfile.is_zipfile(filepath):
                    unzip_pak_file(filepath, DOWNLOAD_FOLDER, message_queue)
            else:
                message_queue.put(("No files found for this mod.\n", "normal"))

            await browser.close()
    
    except Exception as e:
        message_queue.put((f"An error occurred during the download process: {e}\n", "red"))

def run_async_download(game_id, mod_id, oauth_key):
    """
    A separate thread function to run the asyncio download process.
    """
    asyncio.run(download_mod(game_id, mod_id, oauth_key, message_queue))

def start_download_thread(url_entry, status_text, oauth_key):
    """
    Main function to run the download process in a thread to keep the UI responsive.
    """
    if not oauth_key:
        status_text.insert(tk.END, "OAuth key not provided. Cannot proceed with download.\n", "red")
        return

    url = url_entry.get().strip()
    
    # Remove the #description fragment
    url = url.split('#')[0]

    status_text.delete(1.0, tk.END)  # Clear previous messages
    
    if not url:
        status_text.insert(tk.END, "Please enter a mod URL or 'game_id:mod_id'.\n", "normal")
        return
        
    game_id, mod_id = parse_mod_url(url)
    
    if not game_id and not mod_id:
        if re.match(r'^\d+:\d+$', url):
            game_id, mod_id = url.split(":")
        else:
            status_text.insert(tk.END, "Could not parse mod ID from input. Please use a valid URL or the 'game_id:mod_id' format (e.g., '1234:5678').\n", "red")
            return
            
    if game_id and mod_id:
        # Start the download in a new thread
        download_thread = threading.Thread(target=run_async_download, args=(game_id, mod_id, oauth_key))
        download_thread.start()

def check_queue(status_text):
    """
    Check the message queue for new messages and update the UI.
    """
    try:
        while True:
            message, tag = message_queue.get_nowait()
            status_text.insert(tk.END, message, tag)
            status_text.see(tk.END)
    except queue.Empty:
        pass
    finally:
        status_text.after(100, lambda: check_queue(status_text))

# ----------------------
# MAIN UI SCRIPT
# ----------------------
def create_ui():
    """
    Creates the main UI window.
    """
    root = tk.Tk()
    root.title("Mod.io Downloader")
    root.geometry("700x420")
    root.configure(bg="#2c2c2c") # Dark grey background

    # Get the OAuth key upfront
    oauth_key = get_oauth_key(root)
    if not oauth_key:
        root.destroy()
        return

    main_frame = tk.Frame(root, bg="#2c2c2c")
    main_frame.pack(pady=20, padx=20, fill=tk.BOTH, expand=True)

    # Input section
    input_frame = tk.Frame(main_frame, bg="#2c2c2c")
    input_frame.pack(fill=tk.X, pady=10)

    url_label = tk.Label(input_frame, text="Enter mod URL or 'game_id:mod_id':", bg="#2c2c2c", fg="white", font=("Arial", 14))
    url_label.pack(side=tk.LEFT, padx=(0, 10))

    url_entry = tk.Entry(input_frame, width=50, bg="#444444", fg="white", insertbackground="white", relief=tk.FLAT)
    url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Download button
    download_button = tk.Button(main_frame, text="Download Mod", command=lambda: start_download_thread(url_entry, status_text, oauth_key), bg="#555555", fg="white", activebackground="#777777", relief=tk.FLAT, font=("Arial", 14))
    download_button.pack(pady=(10, 0))

    # Status text area
    status_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, bg="#1a1a1a", fg="#00ff00", relief=tk.FLAT, font=("Courier New", 11))
    status_text.pack(pady=10, fill=tk.BOTH, expand=True)
    status_text.tag_config("normal", foreground="#00ff00", font=("Courier New", 11))
    status_text.tag_config("download_finished", foreground="#00ff00", font=("Courier New", 11))
    status_text.tag_config("red", foreground="#ff3333", font=("Courier New", 11))
    
    # Start checking the queue for messages
    check_queue(status_text)

    root.mainloop()

if __name__ == "__main__":
    create_ui()
