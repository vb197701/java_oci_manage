import json
import os
import subprocess
import sys
from pathlib import Path

UPSTREAM = os.environ["UPSTREAM"]
TARGET = os.environ["TARGET"]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"

def api_get(url):
    """GitHub API GET request"""
    import urllib.request
    import urllib.error
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"API Error {e.code}: {e.read().decode()}")
        return None

def api_post(url, data):
    """GitHub API POST request"""
    import urllib.request
    import urllib.error
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode(), 
            headers=headers, 
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"API Error {e.code}: {e.read().decode()}")
        return None

def get_releases(repo, per_page=100):
    """Get all releases from a repository"""
    releases = []
    page = 1
    
    while True:
        url = f"{GITHUB_API}/repos/{repo}/releases?per_page={per_page}&page={page}"
        result = api_get(url)
        
        if not result:
            break
        
        releases.extend(result)
        
        if len(result) < per_page:
            break
        
        page += 1
    
    return releases

def ensure_release(tag, src_release):
    """Create release if it doesn't exist"""
    # First check if release exists
    url = f"{GITHUB_API}/repos/{TARGET}/releases/tags/{tag}"
    existing = api_get(url)
    
    if existing and existing.get("id"):
        print(f"Release {tag} already exists, skipping")
        return True
    
    # Create new release
    data = {
        "tag_name": tag,
        "name": src_release.get("name") or tag,
        "body": src_release.get("body") or f"Synced from upstream {UPSTREAM}",
        "draft": src_release.get("draft", False),
        "prerelease": src_release.get("prerelease", False)
    }
    
    url = f"{GITHUB_API}/repos/{TARGET}/releases"
    result = api_post(url, data)
    
    if result and result.get("id"):
        print(f"Created release {tag}")
        return True
    else:
        print(f"Failed to create release {tag}")
        return False

def sync_assets(release_tag):
    """Sync assets from upstream release to target release"""
    # Get upstream release assets
    url = f"{GITHUB_API}/repos/{UPSTREAM}/releases/tags/{release_tag}"
    upstream_release = api_get(url)
    
    if not upstream_release:
        print(f"Failed to get upstream release {release_tag}")
        return
    
    upstream_assets = upstream_release.get("assets", [])
    if not upstream_assets:
        return
    
    # Get target release
    url = f"{GITHUB_API}/repos/{TARGET}/releases/tags/{release_tag}"
    target_release = api_get(url)
    
    if not target_release:
        print(f"Target release {release_tag} not found, skipping assets")
        return
    
    target_assets = target_release.get("assets", [])
    target_asset_names = {a["name"] for a in target_assets}
    
    # Upload missing assets
    for asset in upstream_assets:
        name = asset["name"]
        download_url = asset["url"]
        
        if name in target_asset_names:
            print(f"Asset {name} already exists, skipping")
            continue
        
        # Download asset
        work = Path("/tmp/release-sync")
        work.mkdir(parents=True, exist_ok=True)
        local_path = work / name
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/octet-stream"
        }
        
        try:
            import urllib.request
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                local_path.write_bytes(response.read())
        except Exception as e:
            print(f"Failed to download asset {name}: {e}")
            continue
        
        # Upload to target release
        upload_url = f"{target_release['upload_url']}?name={name}"
        upload_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/octet-stream"
        }
        
        try:
            import urllib.request
            req = urllib.request.Request(
                upload_url,
                data=local_path.read_bytes(),
                headers=upload_headers,
                method="POST"
            )
            with urllib.request.urlopen(req) as response:
                print(f"Uploaded asset {name}")
        except Exception as e:
            print(f"Failed to upload asset {name}: {e}")

def main():
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN is not set")
        sys.exit(1)
    
    print(f"Syncing releases from {UPSTREAM} to {TARGET}")
    
    # Get upstream releases
    upstream = get_releases(UPSTREAM)
    print(f"Found {len(upstream)} upstream releases")
    
    # Sync each release
    for rel in upstream:
        tag = rel["tag_name"]
        success = ensure_release(tag, rel)
        if success:
            sync_assets(tag)

if __name__ == "__main__":
    main()
