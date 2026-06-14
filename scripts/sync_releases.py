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
        print(f"✗ Command failed: {cmd}")
        print(f"stderr: {result.stderr}")
    return result

def get_releases(repo):
    """Get all releases using gh CLI"""
    r = sh(f'gh release list -R "{repo}" --limit 500', check=False)
    
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
        print(f"✓ Created release {tag}")
        return True
    else:
        print(f"✗ Failed to create release {tag}: {r.stderr}")
        return False

def get_release_assets(repo, release_tag):
    """Get all assets for a release using gh CLI --json"""
    r = sh(f'gh release view "{release_tag}" -R "{repo}" --json assets', check=False)
    
    if r.returncode != 0:
        print(f"Failed to get assets for {release_tag}: {r.stderr}")
        return []
    
    data = json.loads(r.stdout)
    assets = data.get("assets", [])
    
    print(f"Found {len(assets)} assets in upstream release {release_tag}")
    for a in assets:
        print(f"  - {a['name']} ({a['size'] // 1024} KB)")
    
    return assets

def download_asset(repo, release_tag, asset_name, work_dir):
    """Download a single asset"""
    asset_path = work_dir / asset_name
    
    # Skip if already exists
    if asset_path.exists():
        print(f"  - {asset_name} already exists, skipping")
        return True
    
    # Download single asset
    cmd = f'gh release download "{release_tag}" -R "{repo}" -p "{asset_name}" -D "{work_dir}"'
    r = sh(cmd, check=False)
    
    if r.returncode == 0 and asset_path.exists():
        print(f"  ✓ Downloaded {asset_name}")
        return True
    else:
        print(f"  ✗ Failed to download {asset_name}: {r.stderr}")
        return False

def upload_asset(release_tag, repo, asset_path):
    """Upload a single asset"""
    asset_name = asset_path.name
    
    cmd = f'gh release upload "{release_tag}" "{asset_path}" -R "{repo}" --clobber'
    r = sh(cmd, check=False)
    
    if r.returncode == 0:
        print(f"  ✓ Uploaded {asset_name}")
        return True
    else:
        print(f"  ✗ Failed to upload {asset_name}: {r.stderr}")
        return False

def sync_assets(release_tag):
    """Sync all assets from upstream to target"""
    work = Path("/tmp/release-sync")
    work.mkdir(parents=True, exist_ok=True)
    
    # Clean work directory
    for f in work.glob("*"):
        try:
            f.unlink()
        except:
            pass
    
    # Get upstream assets
    upstream_assets = get_release_assets(UPSTREAM, release_tag)
    
    if not upstream_assets:
        print(f"No assets found for release {release_tag}")
        return False
    
    # Download each asset from upstream
    print(f"Downloading assets from upstream...")
    downloaded = []
    for asset in upstream_assets:
        name = asset["name"]
        if download_asset(UPSTREAM, release_tag, name, work):
            downloaded.append(work / name)
    
    if not downloaded:
        print("No assets downloaded")
        return False
    
    print(f"Downloaded {len(downloaded)} assets")
    
    # Upload each asset to target
    print(f"Uploading assets to target...")
    uploaded = 0
    for asset_path in downloaded:
        if upload_asset(release_tag, TARGET, asset_path):
            uploaded += 1
    
    print(f"Uploaded {uploaded}/{len(downloaded)} assets")
    return uploaded > 0

def main():
    print(f"Syncing releases from {UPSTREAM} to {TARGET}")
    print("=" * 60)
    
    upstream = get_releases(UPSTREAM)
    print(f"Found {len(upstream)} upstream releases")
    
    if not upstream:
        print("No upstream releases found")
        sys.exit(1)
    
    success_count = 0
    for idx, rel in enumerate(upstream, 1):
        tag = rel["tag_name"]
        name = rel["name"]
        body = f"Synced from upstream {UPSTREAM}"
        
        print(f"\n[{idx}/{len(upstream)}] Processing release {tag}")
        
        if release_exists(tag, TARGET):
            print(f"  Release {tag} already exists, skipping")
            continue
        
        if create_release(tag, TARGET, name, body):
            if sync_assets(tag):
                success_count += 1
        
        print()
    
    print("=" * 60)
    print(f"Sync complete: {success_count}/{len(upstream)} releases synced successfully")

if __name__ == "__main__":
    main()
