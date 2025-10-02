#!/usr/bin/env python3
"""
Download images from r/Textingtheory without re-downloading duplicates.

State is kept in:
  ~/texting_theory_screenshots/.download_state.json
Fields:
  - seen_post_ids: list of Reddit submission IDs already processed
  - seen_hashes: list of SHA256 hashes of downloaded files
"""
import hashlib
import json
import os
import sys
import time
from urllib.parse import urlparse, unquote

import praw
import requests

# Optional: load .env if available (won't crash if missing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# === Config ===
SUBREDDIT = "Textingtheory"
SAVE_DIR = os.path.join(os.path.expanduser("~"), "texting_theory_screenshots")
STATE_PATH = os.path.join(SAVE_DIR, ".download_state.json")
POST_LIMIT = 100  # change as needed; this is per run

# === Credentials ===
CLIENT_ID = (os.getenv("REDDIT_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.getenv("REDDIT_CLIENT_SECRET") or "").strip()
USER_AGENT = (os.getenv("REDDIT_USER_AGENT") or "textingtheory_downloader/0.1 by u/your_username").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("⚠️  Missing Reddit credentials. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (via .env or env vars).")
    # You can continue unauthenticated for some endpoints, but PRAW prefers creds. Exit to be explicit:
    sys.exit(1)

# === Helpers ===
def ensure_dirs():
    os.makedirs(SAVE_DIR, exist_ok=True)

def load_state():
    if not os.path.exists(STATE_PATH):
        return {"seen_post_ids": [], "seen_hashes": []}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # corrupt or unreadable; start fresh but back up the bad file
        try:
            os.rename(STATE_PATH, STATE_PATH + ".corrupt")
        except Exception:
            pass
        return {"seen_post_ids": [], "seen_hashes": []}

def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)

def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def infer_extension_from_headers(headers, fallback=".jpg"):
    ctype = headers.get("Content-Type", "").lower()
    if "image/png" in ctype:
        return ".png"
    if "image/jpeg" in ctype or "image/jpg" in ctype:
        return ".jpg"
    if "image/gif" in ctype:
        return ".gif"
    if "image/webp" in ctype:
        return ".webp"
    return fallback

def filename_from_url(url: str) -> str:
    # Try to pull a reasonable basename from the URL
    path = urlparse(url).path
    name = os.path.basename(path)
    return unquote(name) or "image"

from urllib.parse import urlparse

REDDIT_IMAGE_HOSTS = {"i.redd.it", "preview.redd.it", "i.reddituploads.com"}

def _normalize_reddit_image_url(u: str) -> str:
    # Keep only scheme, host, and path for reddit image hosts to avoid size/preview variants
    try:
        p = urlparse(u)
        host = p.netloc.lower()
        if host in REDDIT_IMAGE_HOSTS:
            return f"{p.scheme}://{host}{p.path}"
        return u
    except Exception:
        return u

def get_image_urls_from_submission(submission) -> list[str]:
    """
    Prefer the single, highest-quality source.
    - Galleries: use media_metadata["s"]["u"] (the source), not preview 'p' sizes.
    - Single-image reddit posts: use submission.url if it's on i.redd.it.
    - Direct external images: accept .jpg/.png/.gif/.webp.
    - Avoid adding preview URLs if we already have a source.
    """
    urls = []

    # 1) Reddit galleries — use source image only
    try:
        if getattr(submission, "is_gallery", False) and submission.media_metadata:
            for item in submission.gallery_data["items"]:
                media_id = item["media_id"]
                meta = submission.media_metadata.get(media_id, {})
                src = (meta.get("s") or {}).get("u")
                if src and src.startswith("http"):
                    urls.append(src.replace("&amp;", "&"))
            # Return early — gallery handled
            # De-dup below will clean repeats
    except Exception:
        pass

    # 2) Single-image posts on reddit media (i.redd.it)
    if not urls:
        u = submission.url or ""
        if u.startswith("http"):
            host = urlparse(u).netloc.lower()
            if host in REDDIT_IMAGE_HOSTS:
                # Take only this URL, and skip preview later
                urls.append(u)

    # 3) Direct external image links (not reddit-hosted)
    if not urls:
        u = (submission.url or "")
        if u.lower().startswith("http") and any(u.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
            urls.append(u)

    # 4) As a last resort, consider preview **only if** we still have nothing
    if not urls:
        try:
            if submission.preview and "images" in submission.preview:
                for img in submission.preview["images"]:
                    src = img.get("source", {}).get("url")
                    if src and src.startswith("http"):
                        urls.append(src.replace("&amp;", "&"))
                        break  # only one
        except Exception:
            pass

    # Normalize + de-dup
    deduped, seen = [], set()
    for x in urls:
        canon = _normalize_reddit_image_url(x)
        if canon not in seen:
            deduped.append(x)
            seen.add(canon)
    return deduped

def download_and_dedupe(url: str, post_id: str, idx: int, seen_hashes: set[str]) -> str | None:
    """
    Download URL, hash content, skip if hash already seen.
    Returns the saved file path or None if skipped.
    """
    # Conservative headers for Reddit/CDNs
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=30, stream=True)
    r.raise_for_status()

    # Read content into memory to hash (images are usually small enough)
    content = b"".join(r.iter_content(1024 * 64))
    file_hash = sha256_bytes(content)
    if file_hash in seen_hashes:
        return None  # duplicate content

    # Decide filename + extension
    base = filename_from_url(url)
    _, ext = os.path.splitext(base)
    if not ext:
        ext = infer_extension_from_headers(r.headers, fallback=".jpg")

    fname = f"{post_id}_{idx}{ext}"
    fpath = os.path.join(SAVE_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(content)
    return fpath, file_hash

# === Main ===
def main():
    ensure_dirs()
    state = load_state()
    seen_post_ids = set(state.get("seen_post_ids", []))
    seen_hashes = set(state.get("seen_hashes", []))

    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
    )
    reddit.read_only = True

    sub = reddit.subreddit(SUBREDDIT)
    print(f"🔎 Checking r/{SUBREDDIT} (limit={POST_LIMIT})")

    downloaded = 0
    skipped_posts = 0
    skipped_hashes = 0

    for submission in sub.new(limit=POST_LIMIT):
        pid = submission.id

        # Skip if we've processed this post before
        if pid in seen_post_ids:
            skipped_posts += 1
            continue

        urls = get_image_urls_from_submission(submission)
        if not urls:
            # Mark the post as seen to avoid checking it every run
            seen_post_ids.add(pid)
            continue

        found_any_for_post = False
        for i, url in enumerate(urls, start=1):
            try:
                res = download_and_dedupe(url, pid, i, seen_hashes)
                if res is None:
                    skipped_hashes += 1
                    continue
                fpath, h = res
                seen_hashes.add(h)
                downloaded += 1
                found_any_for_post = True
                print(f"✅ Saved {os.path.basename(fpath)}")
                # Be nice to the API/CDN
                time.sleep(0.3)
            except requests.HTTPError as e:
                print(f"❌ HTTP {e.response.status_code} for {url}")
            except Exception as e:
                print(f"❌ Error downloading {url}: {e}")

        # Even if no new file saved (all were dupes), mark post as seen so we don't re-process forever
        seen_post_ids.add(pid)

    # Persist state
    state["seen_post_ids"] = sorted(seen_post_ids)
    state["seen_hashes"] = sorted(seen_hashes)
    save_state(state)

    print("\n— Summary —")
    print(f"New files downloaded: {downloaded}")
    print(f"Posts skipped (already processed): {skipped_posts}")
    print(f"Images skipped as duplicates by hash: {skipped_hashes}")
    print(f"📁 Folder: {SAVE_DIR}")
    print(f"🧠 State:  {STATE_PATH}")

if __name__ == "__main__":
    main()