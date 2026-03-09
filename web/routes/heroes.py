from __future__ import annotations

from typing import Any

from flask import Blueprint, redirect, render_template, request, url_for

from core.config import settings
from core.run_viewer import list_runs
from web.db_context import get_hero_colors_map

heroes_bp = Blueprint("heroes", __name__)


@heroes_bp.get("/heroes")
def heroes_index():
    runs_all = list_runs(settings.run_history_db_path, limit=2000)
    hero_colors = get_hero_colors_map()

    season_raw = (request.args.get("season") or "").strip()

    season_options = sorted(
        {r.get("season_id") for r in runs_all if r.get("season_id") is not None},
        reverse=True,
    )

    if season_raw == "":
        season_selected = ""
        runs = runs_all
    elif season_raw == "__NONE__":
        season_selected = "__NONE__"
        runs = [r for r in runs_all if r.get("season_id") is None]
    else:
        try:
            season_value = int(season_raw)
            season_selected = str(season_value)
            runs = [r for r in runs_all if r.get("season_id") == season_value]
        except ValueError:
            season_selected = ""
            runs = runs_all

    stats: dict[str, dict[str, Any]] = {}
    for r in runs:
        hero = (r.get("hero_effective") or "(unknown)").strip() or "(unknown)"
        s = stats.setdefault(
            hero,
            {
                "hero": hero,
                "runs": 0,
                "verified": 0,
                "wins": 0,
                "wins_vals": [],
            },
        )
        s["runs"] += 1
        if r.get("is_confirmed"):
            s["verified"] += 1
            if r.get("won"):
                s["wins"] += 1
            if r.get("wins") is not None:
                s["wins_vals"].append(int(r["wins"]))

    out = []
    for hero, s in stats.items():
        verified = int(s["verified"])
        wins = int(s["wins"])
        wins_vals = s.get("wins_vals") or []
        out.append(
            {
                "hero": s["hero"],
                "runs": s["runs"],
                "wins": wins,
                "winrate": (wins * 100 / verified) if verified else 0.0,
                "avg_wins": (sum(wins_vals) / len(wins_vals)) if wins_vals else 0.0,
                "color": hero_colors.get(hero),
            }
        )

    out.sort(key=lambda x: (-x["runs"], x["hero"].lower()))
    return render_template(
        "heroes.html",
        heroes=out,
        hero_colors=hero_colors,
        season_options=season_options,
        season_selected=season_selected,
    )


@heroes_bp.get("/heroes/<hero>")
def hero_page(hero: str):
    hero = (hero or "").strip()
    if not hero:
        return redirect(url_for("heroes.heroes_index"))

    runs_all = list_runs(settings.run_history_db_path, limit=2000)
    hero_colors = get_hero_colors_map()
    color = hero_colors.get(hero)

    season_options = sorted(
        {r.get("season_id") for r in runs_all if r.get("season_id") is not None},
        reverse=True,
    )

    season_raw = (request.args.get("season") or "").strip()

    runs = [r for r in runs_all if (r.get("hero_effective") or "(unknown)") == hero]

    if season_raw == "":
        season_selected = ""
    elif season_raw == "__NONE__":
        season_selected = "__NONE__"
        runs = [r for r in runs if r.get("season_id") is None]
    else:
        try:
            season_value = int(season_raw)
            season_selected = str(season_value)
            runs = [r for r in runs if r.get("season_id") == season_value]
        except ValueError:
            season_selected = ""

    verified = [r for r in runs if r.get("is_confirmed")]
    verified_count = len(verified)

    def outcome(r: dict) -> str:
        if r.get("won") is True:
            return "W"
        if r.get("wins") is not None:
            return "L"
        return "?"

    wins = sum(1 for r in verified if outcome(r) == "W")
    losses = sum(1 for r in verified if outcome(r) == "L")
    unknown = sum(1 for r in verified if outcome(r) == "?")

    winrate = (wins * 100 / verified_count) if verified_count else 0.0

    last10 = verified[:10]
    last10_str = "".join(outcome(r) for r in last10)

    cur_type = None
    cur_len = 0
    for r in verified:
        ch = outcome(r)
        if ch == "?":
            break
        if cur_type is None:
            cur_type = ch
            cur_len = 1
        elif ch == cur_type:
            cur_len += 1
        else:
            break

    best_win = 0
    w_run = 0
    for r in verified:
        ch = outcome(r)
        if ch == "W":
            w_run += 1
            best_win = max(best_win, w_run)
        elif ch in ("L", "?"):
            w_run = 0

    wins_vals = [int(r["wins"]) for r in verified if r.get("wins") is not None]
    avg_wins = (sum(wins_vals) / len(wins_vals)) if wins_vals else 0.0

    return render_template(
        "hero.html",
        hero=hero,
        color=color,
        runs=runs,
        verified_count=verified_count,
        wins=wins,
        losses=losses,
        unknown=unknown,
        winrate=winrate,
        avg_wins=avg_wins,
        last10_str=last10_str,
        streaks={"current_type": cur_type, "current_len": cur_len, "best_win": best_win},
        hero_colors=hero_colors,
        season_options=season_options,
        season_selected=season_selected,
    )
