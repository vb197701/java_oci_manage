import json
import os
import subprocess
import sys
from pathlib import Path

UPSTREAM = os.environ["UPSTREAM"]
TARGET = os.environ["TARGET"]

def sh(cmd, check=True):
    return subprocess.run(cmd, shell=True, check=check, text=True, capture_output=True)

def gh_json(args):
    r = sh(f'gh {args} --json tagName,name,body,isDraft,isPrerelease,createdAt,publishedAt,assets')
    return json.loads(r.stdout or "[]")

def ensure_release(tag, src):
    view = subprocess.run(f'gh release view "{tag}" -R "{TARGET}" >/dev/null 2>&1', shell=True)
    if view.returncode == 0:
        return

    title = src.get("name") or tag
    body = src.get("body") or f"Synced from upstream {UPSTREAM}"
    prerelease = "--prerelease" if src.get("isPrerelease") else ""
    draft = "--draft" if src.get("isDraft") else ""
    cmd = f'gh release create "{tag}" -R "{TARGET}" --title "{title}" --notes {json.dumps(body)} {prerelease} {draft}'
    sh(cmd)

def sync_assets(tag):
    out = sh(f'gh release view "{tag}" -R "{UPSTREAM}" --json assets').stdout
    assets = json.loads(out).get("assets", [])
    if not assets:
        return

    work = Path("/tmp/release-sync")
    work.mkdir(parents=True, exist_ok=True)

    for a in assets:
        name = a["name"]
        url = a["url"]
        local = work / name
        sh(f'gh release download "{tag}" -R "{UPSTREAM}" -p "{name}" -D "{work}"')
        existing = sh(f'gh release view "{tag}" -R "{TARGET}" --json assets').stdout
        existing_assets = {x["name"] for x in json.loads(existing).get("assets", [])}
        if name not in existing_assets:
            sh(f'gh release upload "{tag}" "{local}" -R "{TARGET}" --clobber')

def main():
    upstream = gh_json(f'release list -R "{UPSTREAM}" --limit 200')
    target = gh_json(f'release list -R "{TARGET}" --limit 200')
    target_tags = {x["tagName"] for x in target}

    for rel in upstream:
        tag = rel["tagName"]
        ensure_release(tag, rel)
        sync_assets(tag)

if __name__ == "__main__":
    main()
