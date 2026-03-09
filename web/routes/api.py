from __future__ import annotations

import os

from flask import Blueprint, abort, jsonify, request, send_file

from core.config import settings
from core.run_viewer import search_templates
from web.db_context import get_templates_conn

api_bp = Blueprint("api", __name__)


@api_bp.get("/api/templates")
def api_templates():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    size = (request.args.get("size") or "").strip().lower()
    if size not in ("small", "medium", "large"):
        size = ""

    rows = search_templates(settings.templates_db_path, q, limit=6, size=size)
    out = [
        {
            "template_id": r["template_id"],
            "name": r["name"],
            "size": r.get("size"),
        }
        for r in rows
    ]
    return jsonify(out)


@api_bp.get("/item-image/<template_id>")
def item_image(template_id: str):
    conn = get_templates_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT image_path FROM templates WHERE template_id = ? AND COALESCE(ignored, 0) = 0",
        (template_id,),
    )
    row = cur.fetchone()
    if not row or not row["image_path"]:
        abort(404)

    path = row["image_path"]
    if not os.path.isabs(path):
        path = os.path.abspath(path)

    if not os.path.exists(path):
        abort(404)

    return send_file(path, mimetype="image/webp")
