from __future__ import annotations

import os
import platform
import argparse
import json
import sqlite3
from typing import Any, Dict, List, Optional
import tempfile
import zipfile

from core.config import settings
from core.templates_db import TemplatesDb


def default_game_data_path() -> Optional[str]:
    """
    Default to Windows install path.
    On non-Windows systems, return None.
    """
    if platform.system() == "Windows":
        return (
            r"C:\Program Files (x86)\Steam\steamapps\common"
            r"\The Bazaar\TheBazaar_Data\StreamingAssets\GameData.db.zip"
        )

    return None


def ensure_ignored_column(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(templates)")
        cols = {row[1] for row in cur.fetchall()}
        if "ignored" not in cols:
            cur.execute("ALTER TABLE templates ADD COLUMN ignored INTEGER DEFAULT 0")
            conn.commit()
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import The Bazaar templates from GameData.db.zip")

    p.add_argument(
        "game_data_zip",
        nargs="?",
        default=default_game_data_path(),
        help="Path to GameData.db.zip",
    )

    p.add_argument(
        "--db",
        dest="db_path",
        default=settings.templates_db_path,
        help="Output sqlite DB path for templates",
    )

    return p.parse_args()


def ignore_duplicate_debug_variants(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT name
            FROM templates
            WHERE name IS NOT NULL
            GROUP BY name
            HAVING COUNT(*) > 1
            """
        )
        dup_names = [r["name"] for r in cur.fetchall()]

        changed = 0

        for name in dup_names:
            cur.execute(
                """
                SELECT template_id, internal_name
                FROM templates
                WHERE name = ?
                """,
                (name,),
            )
            rows = cur.fetchall()

            for r in rows:
                internal_name = (r["internal_name"] or "").strip()
                if "[" in internal_name:
                    cur.execute(
                        """
                        UPDATE templates
                        SET ignored = 1
                        WHERE template_id = ?
                        """,
                        (r["template_id"],),
                    )
                    changed += 1

        conn.commit()
        return changed
    finally:
        conn.close()


def should_import_item(name: str) -> bool:
    """Filter obvious non-game items from cards.json."""
    name = name.strip()

    if not name:
        return False

    if "[" in name:
        return False

    if "TEMPLATE" in name.upper():
        return False

    if "DEBUG" in name.upper():
        return False

    return True


def _safe_get_title_text(card: Dict[str, Any]) -> Optional[str]:
    loc = card.get("Localization")
    if isinstance(loc, dict):
        title = loc.get("Title")
        if isinstance(title, dict):
            txt = title.get("Text")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    return None


def extract_db(zip_path: str) -> str:
    temp_dir = tempfile.mkdtemp()

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_dir)

    return os.path.join(temp_dir, "GameData.db")


def iter_cards_from_sqlite(db_file: str):

    conn = sqlite3.connect(db_file)

    try:
        cur = conn.cursor()

        cur.execute("SELECT Id, Data FROM cards")

        for row in cur.fetchall():

            card_id, raw_data = row

            try:
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")

                card = json.loads(raw_data)

                if not isinstance(card, dict):
                    continue

                yield card

            except Exception as e:
                print(f"Failed to parse card {card_id}: {e}")

    finally:
        conn.close()


# ------------------------------------------------------------
# Core callable function
# ------------------------------------------------------------

def import_templates_from_cards(
    cards_json: str,
    db_path: str,
) -> dict[str, Any]:


    game_data_db = extract_db(cards_json)
    
    all_rows: List[Dict[str, Any]] = []
    total_cards = 0
    total_items = 0
    skipped_templates = 0
    
    for card in iter_cards_from_sqlite(game_data_db):
    
        total_cards += 1

        if not isinstance(card, dict):
            continue

        if card.get("Type") != "Item":
            continue

        template_id = card.get("Id")
        if not isinstance(template_id, str) or not template_id:
            continue

        total_items += 1

        name = _safe_get_title_text(card) or card.get("InternalName") or template_id
        if not isinstance(name, str):
            name = str(name)

        if not should_import_item(name):
            skipped_templates += 1
            continue

        size = card.get("Size")
        if isinstance(size, str):
            size = size.lower()
        else:
            size = None

        heroes = card.get("Heroes")
        if not isinstance(heroes, list):
            heroes = []
        heroes = [h.strip() for h in heroes if isinstance(h, str)]

        tags = card.get("Tags")
        if not isinstance(tags, list):
            tags = []
        tags = [t for t in tags if isinstance(t, str)]

        art_key = card.get("ArtKey")
        if not isinstance(art_key, str):
            art_key = None

        internal_name = card.get("InternalName")
        if not isinstance(internal_name, str):
            internal_name = None

        version = card.get("Version")
        if not isinstance(version, str):
            version = "unknown"


        all_rows.append(
            {
                "template_id": template_id,
                "name": name,
                "size": size,
                "heroes_json": json.dumps(heroes, ensure_ascii=False),
                "tags_json": json.dumps(tags, ensure_ascii=False),
                "art_key": art_key,
                "internal_name": internal_name,
                "version": version,
            }
        )

    db = TemplatesDb(db_path)

    try:
        chunk_size = 1000

        for i in range(0, len(all_rows), chunk_size):
            db.upsert_templates(all_rows[i : i + chunk_size])

    finally:
        db.close()

    ensure_ignored_column(db_path)
    duplicates_ignored = ignore_duplicate_debug_variants(db_path)

    return {
        "ok": True,
        "message": "Templates imported",
        "source": cards_json,
        "db": db_path,
        "cards_seen": total_cards,
        "items_imported": len(all_rows),
        "templates_skipped": skipped_templates,
        "duplicates_ignored": duplicates_ignored,
    }
    

# ------------------------------------------------------------
# CLI wrapper
# ------------------------------------------------------------

def main() -> None:
    args = parse_args()

    result = import_templates_from_cards(
        cards_json=args.game_data_zip,
        db_path=args.db_path,
    )

    print(
        {
            "type": "TemplatesImported",
            "source": result["source"],
            "db": result["db"],
            "cards_seen": result["cards_seen"],
            "items_imported": result["items_imported"],
            "templates_skipped": result["templates_skipped"],
            "duplicates_ignored": result["duplicates_ignored"],
        }
    )


if __name__ == "__main__":
    main()
