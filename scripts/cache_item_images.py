from __future__ import annotations

import argparse
import os
import re
import sqlite3
import time
import urllib.parse
from typing import Optional, Tuple

import requests
import certifi

# Identify ourselves politely; keep requests rate-limited with --sleep
UA = "BazaarTracker/0.1 (local image cache builder; respectful scraping)"

# Canonical BazaarDB card path looks like: /card/<id>/<name>
# The <id> is long (not 4-8 chars), so require 12+ to avoid truncated matches.
CARD_CANON_RE = re.compile(
    r"(/card/[a-z0-9]{12,}/[^\"'<>\\s]+)",
    re.IGNORECASE,
)

# CDN URLs should include an extension; otherwise we risk capturing partial strings.
CDN_IMAGE_RE = re.compile(
    r"(https?://s\.bazaardb\.gg/[^\"'<>]+?\.(?:webp|png|jpe?g))",
    re.IGNORECASE,
)

OG_IMAGE_RE = re.compile(
    r'<meta\s+property=["\']og:image["\']\s+content=["\'](?P<url>https?://s\.bazaardb\.gg/[^"\']+)["\']',
    re.IGNORECASE,
)


def _clean_url(u: str) -> str:
    u = re.sub(r"\s+", "", u).strip()
    return u.split("?")[0]


def fetch_text(url: str, timeout: int) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=timeout,
        verify=certifi.where(),
    )
    r.raise_for_status()
    return r.text


def fetch_bytes(url: str, timeout: int) -> bytes:
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=timeout,
        verify=certifi.where(),
    )
    r.raise_for_status()
    return r.content


def resolve_bazaardb_image_url(name: str, timeout: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (card_url, image_url) or (None, None).

    Strategy:
      1) Search page: extract canonical /card/<longid>/<slug> path
      2) Card page: prefer og:image, else any CDN image URL with a real extension
      3) Sanitize URLs by removing whitespace/newlines
    """
    q = urllib.parse.quote(f'"{name}"')
    search_url = f"https://bazaardb.gg/search?c=items&q={q}"
    search_html = fetch_text(search_url, timeout=timeout)

    matches = CARD_CANON_RE.findall(search_html)
    
    if not matches:
        return None, None
    
    name_slug = name.lower().replace(" ", "-")
    
    card_path = None
    for m in matches:
        if name_slug in m.lower():
            card_path = m
            break
    
    if not card_path:
        card_path = matches[0]
    
    card_url = _clean_url("https://bazaardb.gg" + card_path)

    card_html = fetch_text(card_url, timeout=timeout)

    # 1) Best: og:image meta tag
    m_og = OG_IMAGE_RE.search(card_html)
    if m_og:
        return card_url, _clean_url(m_og.group("url"))

    # 2) Fallback: any CDN URL that actually looks like an image (has extension)
    cdn_urls = [_clean_url(m2.group(1)) for m2 in CDN_IMAGE_RE.finditer(card_html)]
    if not cdn_urls:
        return card_url, None

    # Prefer webp > png > jpg
    def score(u: str) -> int:
        u2 = u.lower()
        if u2.endswith(".webp"):
            return 3
        if u2.endswith(".png"):
            return 2
        if u2.endswith(".jpg") or u2.endswith(".jpeg"):
            return 1
        return 0

    cdn_urls.sort(key=score, reverse=True)
    return card_url, cdn_urls[0]


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def ensure_image_path_column(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(templates)")
    cols = {row[1] for row in cur.fetchall()}  # row[1] is column name
    if "image_path" not in cols:
        cur.execute("ALTER TABLE templates ADD COLUMN image_path TEXT")
        conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Cache BazaarDB item images locally keyed by template_id")
    ap.add_argument("--db", required=True, help="Path to templates sqlite db (e.g. db/templates.sqlite3)")
    ap.add_argument("--out-dir", default="assets/images/items", help="Where to store downloaded images")
    ap.add_argument("--sleep", type=float, default=0.7, help="Delay between items (seconds)")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N successful downloads (0 = no limit)")
    ap.add_argument("--force", action="store_true", help="Re-download even if image_path already set")
    ap.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    args = ap.parse_args()

    # Ensure output directory exists
    ensure_dir(args.out_dir)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    ensure_image_path_column(conn)

    cur = conn.cursor()

    if args.force:
        cur.execute("SELECT template_id, name FROM templates ORDER BY name ASC")
    else:
        cur.execute(
            "SELECT template_id, name FROM templates WHERE image_path IS NULL OR image_path='' ORDER BY name ASC"
        )

    rows = cur.fetchall()
    print(f"Need images for: {len(rows)} items")

    ok = 0
    for r in rows:
        template_id = str(r["template_id"])
        name = str(r["name"])

        # Store file on disk under out-dir.
        # Store a *relative* path in the DB so it works across machines.
        filename = f"{template_id}.webp"
        disk_path = os.path.join(args.out_dir, filename)

        db_path = os.path.join("assets", "images", "items", filename).replace("\\", "/")

        # If the file already exists and we're not forcing, just set DB path if missing.
        if (not args.force) and os.path.exists(disk_path):
            cur.execute("UPDATE templates SET image_path=? WHERE template_id=?", (db_path, template_id))
            conn.commit()
            print(f"[SKIP] {name} already on disk -> {db_path}")
            continue

        try:
            card_url, img_url = resolve_bazaardb_image_url(name, timeout=args.timeout)
            if not img_url:
                print(f"[MISS] {name} ({template_id}) card={card_url}")
                time.sleep(args.sleep)
                continue

            data = fetch_bytes(img_url, timeout=max(args.timeout, 60))
            with open(disk_path, "wb") as f:
                f.write(data)

            cur.execute("UPDATE templates SET image_path=? WHERE template_id=?", (db_path, template_id))
            conn.commit()

            ok += 1
            print(f"[OK] {name} -> {db_path}")

            if args.limit and ok >= args.limit:
                break

        except Exception as e:
            print(f"[FAIL] {name} ({template_id}): {e}")

        time.sleep(args.sleep)

    print(f"Downloaded {ok} images")
    conn.close()


if __name__ == "__main__":
    main()
