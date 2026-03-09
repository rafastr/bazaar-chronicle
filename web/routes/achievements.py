from __future__ import annotations

from flask import Blueprint, render_template

from web.db_context import get_db

achievements_bp = Blueprint("achievements", __name__)


@achievements_bp.get("/achievements")
def achievements_view():
    db = get_db()
    cur = db.conn.cursor()
    cur.execute(
        """
        SELECT
          a.key,
          a.title,
          a.description,
          u.unlocked_at_unix,
          u.run_id
        FROM achievements a
        LEFT JOIN achievement_unlocks u ON u.key = a.key
        ORDER BY
          CASE WHEN u.unlocked_at_unix IS NOT NULL THEN 0 ELSE 1 END,
          u.unlocked_at_unix DESC,
          a.title COLLATE NOCASE ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]

    unlocked = sum(1 for r in rows if r.get("unlocked_at_unix") is not None)
    total = len(rows)

    return render_template(
        "achievements.html",
        achievements=rows,
        unlocked=unlocked,
        total=total,
    )
