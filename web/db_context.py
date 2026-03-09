from __future__ import annotations

import sqlite3

from flask import g

from core.config import settings
from core.run_history_db import RunHistoryDb
from core.templates_db import TemplatesDb



def get_db() -> RunHistoryDb:
    db = g.get("run_history_db")
    if db is None:
        # Make schema exists even if user only runs the web UI
        db = RunHistoryDb(settings.run_history_db_path)
        g.run_history_db = db
    return db


# One templates sqlite connection per request (avoid scattered sqlite3.connect calls in routes).
def get_templates_conn() -> sqlite3.Connection:
    conn = g.get("templates_conn")
    if conn is None:
        # Ensure the templates DB file and schema exist
        tdb = TemplatesDb(settings.templates_db_path)
        tdb.close()

        conn = sqlite3.connect(settings.templates_db_path)
        conn.row_factory = sqlite3.Row
        g.templates_conn = conn
    return conn



def close_db(exception=None):
    db = getattr(g, "run_history_db", None)
    if db is not None:
        try:
            db.close()
        finally:
            g.run_history_db = None

    tconn = getattr(g, "templates_conn", None)
    if tconn is not None:
        try:
            tconn.close()
        finally:
            g.templates_conn = None


def get_hero_colors_map() -> dict[str, str]:
    db = get_db()
    cur = db.conn.cursor()
    cur.execute("SELECT hero, color FROM hero_colors")
    return {r["hero"]: r["color"] for r in cur.fetchall() if r["hero"] and r["color"]}

