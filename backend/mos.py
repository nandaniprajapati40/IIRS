import os
import requests
from bs4 import BeautifulSoup

# CONFIG
USERNAME = "nandani"  # Replace with your actual username
PASSWORD = "Qvb#1234"   # Replace with your actual password (no backslash)

ORDER_URL = "https://www.mosdac.gov.in/order/Apr26_177988"

SAVE_DIR = "/home/aman-/aman/irrigation/backend/data/raw/insat_rain_hdf"
os.makedirs(SAVE_DIR, exist_ok=True)

BASE_URL = "https://www.mosdac.gov.in"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

def login():
    print("🔐 Logging in...")
    login_url = BASE_URL + "/login"
    
    # Get login page first (for CSRF token if needed)
    login_page = session.get(login_url)
    soup = BeautifulSoup(login_page.text, "html.parser")
    
    # Look for CSRF token (common pattern)
    csrf_token = None
    csrf_input = soup.find("input", {"name": ["csrf_token", "csrf", "_token"]})
    if csrf_input:
        csrf_token = csrf_input.get("value")
    
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    if csrf_token:
        payload["csrf_token"] = csrf_token
    
    response = session.post(login_url, data=payload, allow_redirects=True)
    
    # Check if login succeeded
    if "logout" in response.text.lower() or "dashboard" in response.text.lower():
        print("✅ Login successful")
        return True
    else:
        print("❌ Login failed - check your credentials")
        return False

def download_file(url):
    filename = url.split("/")[-1]
    filepath = os.path.join(SAVE_DIR, filename)
    
    if os.path.exists(filepath):
        print(f"⏭ Already exists: {filename}")
        return
    
    print(f"⬇ Downloading: {filename}")
    
    try:
        response = session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Get file size for progress indication
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        print(f"\r  Progress: {progress:.1f}%", end="")
        
        print(f"\n✅ Saved: {filename} ({total_size/1024/1024:.2f} MB)")
    
    except Exception as e:
        print(f"\n❌ Failed: {filename} - {str(e)}")

def main():
    # Login first
    if not login():
        print("Cannot proceed without login")
        return
    
    # Get order page
    print("🔎 Fetching order page...")
    response = session.get(ORDER_URL)
    
    if response.status_code != 200:
        print(f"❌ Failed to access order page: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find all HDF5 files
    links = []
    for link in soup.find_all("a"):
        href = link.get("href")
        if href and (".h5" in href or ".hdf" in href or ".hdf5" in href):
            if not href.startswith("http"):
                href = BASE_URL + href
            links.append(href)
    
    print(f"📦 Found {len(links)} files to download")
    
    # Download each file
    for idx, link in enumerate(links, 1):
        print(f"\n[{idx}/{len(links)}]")
        download_file(link)
    
    print(f"\n🎯 All files saved to: {SAVE_DIR}")

if __name__ == "__main__":
    main()