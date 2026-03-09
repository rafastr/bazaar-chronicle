from __future__ import annotations

from flask import Blueprint, render_template

from core.config import settings
from web.db_context import get_db, get_hero_colors_map, get_templates_conn
from web.services import get_item_checklist

items_bp = Blueprint("items", __name__)


@items_bp.get("/items")
def items_view():
    items = get_item_checklist(
        settings.templates_db_path,
        settings.run_history_db_path,
        tconn=get_templates_conn(),
        hconn=get_db().conn,
    )
    hero_colors = get_hero_colors_map()
    return render_template("items_view.html", items=items, hero_colors=hero_colors)
