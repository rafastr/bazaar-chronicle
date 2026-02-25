import os
import sqlite3
from typing import Any, Dict, List, Optional

from .run_history_db import RunHistoryDb


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_runs(run_history_db_path: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    List recent runs with effective hero/rank (applies overrides when present).
    """

    # Ensure schema exists (so running --last-run before watch mode still works)
    tmp = RunHistoryDb(run_history_db_path)
    tmp.close()

    conn = _connect(run_history_db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                r.run_id,
                r.ended_at_unix,
                r.screenshot_path,

                -- base values
                r.hero AS hero_base,
                r.rank AS rank_base,

                -- overrides (nullable)
                o.hero_override,
                o.rank_override,
                o.is_confirmed,
                o.notes,

                -- effective values
                COALESCE(o.hero_override, r.hero) AS hero_effective,
                COALESCE(o.rank_override, r.rank) AS rank_effective
            FROM runs r
            LEFT JOIN run_overrides o ON o.run_id = r.run_id
            ORDER BY r.run_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_last_run_id(run_history_db_path: str) -> Optional[int]:
    # Ensure schema exists (so running --last-run before watch mode still works)
    tmp = RunHistoryDb(run_history_db_path)
    tmp.close()

    conn = _connect(run_history_db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT run_id
            FROM runs
            ORDER BY run_id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return int(row["run_id"]) if row else None
    finally:
        conn.close()


def get_run_board(
    run_history_db_path: str,
    templates_db_path: str,
    run_id: int,
) -> Dict[str, Any]:

    # Ensure schema exists (so running --last-run before watch mode still works)
    tmp = RunHistoryDb(run_history_db_path)
    tmp.close()

    rh = _connect(run_history_db_path)
    td = _connect(templates_db_path)
    try:
        cur = rh.cursor()
        cur.execute(
            "SELECT run_id, ended_at_unix, screenshot_path, hero, rank FROM runs WHERE run_id = ?",
            (run_id,),
        )
        run_row = cur.fetchone()
        if not run_row:
            raise RuntimeError(f"Run {run_id} not found in {run_history_db_path}")

        cur.execute(
            """
            SELECT socket_number, template_id, size
            FROM run_items
            WHERE run_id = ?
            ORDER BY socket_number ASC
            """,
            (run_id,),
        )
        items = cur.fetchall()

        cur.execute(
                "SELECT hero_override, rank_override, notes, is_confirmed FROM run_overrides WHERE run_id=?",
                (run_id,),
                )
        ov = cur.fetchone()

        hero_eff = (ov["hero_override"] if ov and ov["hero_override"] else run_row["hero"])
        rank_eff = (ov["rank_override"] if ov and ov["rank_override"] is not None else run_row["rank"])
        notes = (ov["notes"] if ov else None)
        is_confirmed = (ov["is_confirmed"] if ov else 0)

        cur.execute(
            """
            SELECT socket_number, template_id_override, size_override, note
            FROM run_item_overrides
            WHERE run_id=?
            """,
            (run_id,),
        )
        ov_items = {int(r["socket_number"]): dict(r) for r in cur.fetchall()}

        # Resolve names from templates DB (if template_id not null)
        resolved_items: List[Dict[str, Any]] = []
        tcur = td.cursor()

        for it in items:
            base_template_id = it["template_id"]
            base_size = it["size"]

            ovi = ov_items.get(int(it["socket_number"]))
            template_eff = base_template_id
            size_eff = base_size
            override_note = None

            if ovi:
                # If the override column exists (even if NULL), apply it.
                # We store "clear override" by deleting the override row via clear_item_override().
                if ovi.get("template_id_override") is not None:
                    template_eff = ovi.get("template_id_override")
                if ovi.get("size_override") is not None:
                    size_eff = ovi.get("size_override")
                override_note = ovi.get("note")

            name: Optional[str] = None
            art_key: Optional[str] = None

            # Resolve using EFFECTIVE template id (not base)
            if template_eff:
                tcur.execute(
                    "SELECT name, art_key FROM templates WHERE template_id = ?",
                    (template_eff,),
                )
                trow = tcur.fetchone()
                if trow:
                    name = trow["name"]
                    art_key = trow["art_key"]

            resolved_items.append(
                {
                    "socket_number": it["socket_number"],
                    "size": size_eff,
                    "template_id": template_eff,
                    "name": name,
                    "art_key": art_key,

                    # debug fields (helpful)
                    "base_template_id": base_template_id,
                    "base_size": base_size,
                    "overridden": bool(ovi),
                    "override_note": override_note,
                }
            )

        return {
            "run_id": run_row["run_id"],
            "ended_at_unix": run_row["ended_at_unix"],
            "screenshot_path": run_row["screenshot_path"],
        
            "hero": run_row["hero"],
            "rank": run_row["rank"],
        
            "hero_effective": hero_eff,
            "rank_effective": rank_eff,
            "notes": notes,
            "is_confirmed": is_confirmed,
        
            "items": resolved_items,
        }

    finally:
        rh.close()
        td.close()


def search_templates(templates_db_path: str, q: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = _connect(templates_db_path)
    try:
        cur = conn.cursor()
        like = f"%{q}%"
        cur.execute(
            """
            SELECT template_id, name, size, art_key
            FROM templates
            WHERE name LIKE ?
            ORDER BY name ASC
            LIMIT ?
            """,
            (like, limit),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
