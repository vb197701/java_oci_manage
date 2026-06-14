import json
import os
import subprocess
import sys
from pathlib import Path

UPSTREAM = os.environ["UPSTREAM"]
TARGET = os.environ["TARGET"]

def sh(cmd, check=True):
    """Run shell command"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"stderr: {result.stderr}")
    return result

def get_releases(repo):
    """Get all releases using gh CLI"""
    sh_cmd = f'gh release list -R "{repo}" --limit 500'
    r = sh(sh_cmd, check=False)
    
    if r.returncode != 0:
        print(f"Failed to get releases: {r.stderr}")
        return []
    
    releases = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        tag = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else tag
        releases.append({"tag_name": tag, "name": name})
    
    return releases

def release_exists(tag, repo):
    """Check if release exists"""
    r = sh(f'gh release view "{tag}" -R "{repo}" >/dev/null 2>&1', check=False)
    return r.returncode == 0

def create_release(tag, repo, name, body, prerelease=False, draft=False):
    """Create a new release"""
    prerelease_flag = "--prerelease" if prerelease else ""
    draft_flag = "--draft" if draft else ""
    
    cmd = f'''gh release create "{tag}" -R "{repo}" \
        --title "{name}" \
        --notes "{body}" \
        {prerelease_flag} \
        {draft_flag}'''
    
    r = sh(cmd, check=False)
    if r.returncode == 0:
        print(f"Created release {tag}")
        return True
    else:
        print(f"Failed to create release {tag}: {r.stderr}")
        return False

def sync_assets(release_tag):
    """Sync assets using gh CLI"""
    work = Path("/tmp/release-sync")
    work.mkdir(parents=True, exist_ok=True)
    
    # Clean work directory
    for f in work.glob("*"):
        f.unlink()
    
    # Download all assets from upstream
    print(f"Downloading assets from upstream release {release_tag}")
    download_cmd = f'gh release download "{release_tag}" -R "{UPSTREAM}" -D "{work}"'
    r = sh(download_cmd, check=False)
    
    if r.returncode != 0:
        print(f"Failed to download assets from upstream: {r.stderr}")
        return False
    
    # List downloaded files
    assets = list(work.glob("*"))
    if not assets:
        print(f"No assets found for release {release_tag}")
        return False
    
    print(f"Found {len(assets)} assets to upload")
    
    # Upload each asset to target
    for asset in assets:
        name = asset.name
        upload_cmd = f'gh release upload "{release_tag}" "{asset}" -R "{TARGET}" --clobber'
        r = sh(upload_cmd, check=False)
        
        if r.returncode == 0:
            print(f"✓ Uploaded asset {name}")
        else:
            print(f"✗ Failed to upload asset {name}: {r.stderr}")
    
    return True

def main():
    print(f"Syncing releases from {UPSTREAM} to {TARGET}")
    
    # Get upstream releases
    upstream = get_releases(UPSTREAM)
    print(f"Found {len(upstream)} upstream releases")
    
    if not upstream:
        print("No upstream releases found")
        sys.exit(1)
    
    # Sync each release
    success_count = 0
    for rel in upstream:
        tag = rel["tag_name"]
        name = rel["name"]
        body = f"Synced from upstream {UPSTREAM}"
        
        if release_exists(tag, TARGET):
            print(f"Release {tag} already exists, skipping")
            continue
        
        if create_release(tag, TARGET, name, body):
            if sync_assets(tag):
                success_count += 1
    
    print(f"\nSync complete: {success_count}/{len(upstream)} releases synced successfully")

if __name__ == "__main__":
    main()
