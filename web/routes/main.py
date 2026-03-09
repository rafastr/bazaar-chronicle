from __future__ import annotations

from flask import Blueprint, render_template, request

from core.config import settings
from web.db_context import get_db, get_hero_colors_map, get_templates_conn
from web.services import build_index_context, get_hero_list, get_item_checklist

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    season_raw = (request.args.get("season") or "").strip()

    ctx = build_index_context(
        settings=settings,
        get_db=get_db,
        get_templates_conn=get_templates_conn,
        hero_colors_map=get_hero_colors_map,
        get_item_checklist=get_item_checklist,
        get_hero_list=get_hero_list,
        season_filter=season_raw,
    )
    return render_template("index.html", **ctx)
