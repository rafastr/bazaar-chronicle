from __future__ import annotations

from typing import Optional

from core.config import settings
from core.run_history_db import RunHistoryDb


def _rebuild_after_edit(db: RunHistoryDb) -> None:
    """
    Rebuild all derived state that depends on effective run data.
    """
    db.rebuild_item_hero_wins()
    db.rebuild_item_firsts(settings.templates_db_path)
    db.rebuild_achievements(settings.templates_db_path)


def confirm_run(run_id: int, confirmed: bool = True) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        db.confirm_run(int(run_id), confirmed=bool(confirmed), templates_db_path=settings.templates_db_path)
        _rebuild_after_edit(db)
    finally:
        db.close()


def set_hero_override(run_id: int, hero: Optional[str]) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        hero_clean = (hero or "").strip()
        if hero_clean:
            db.set_run_hero_override(int(run_id), hero_clean)
        else:
            db.clear_run_hero_override(int(run_id))
        _rebuild_after_edit(db)
    finally:
        db.close()


def set_rank_override(run_id: int, rank: Optional[int]) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        if rank is None:
            db.clear_run_rank_override(int(run_id))
        else:
            db.set_run_rank_override(int(run_id), int(rank))
        _rebuild_after_edit(db)
    finally:
        db.close()


def set_run_notes(run_id: int, notes: Optional[str]) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        notes_clean = (notes or "").strip()
        db.set_run_notes(int(run_id), notes_clean)
        # notes do not affect derived stats
    finally:
        db.close()


def set_item_override(
    run_id: int,
    socket_number: int,
    template_id: Optional[str],
    size: Optional[str] = None,
    note: Optional[str] = None,
) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        template_id_clean = (template_id or "").strip() or None
        size_clean = (size or "").strip().lower() or None
        note_clean = (note or "").strip() or None

        db.upsert_item_override(
            int(run_id),
            int(socket_number),
            template_id_override=template_id_clean,
            size_override=size_clean,
            note=note_clean,
        )
        _rebuild_after_edit(db)
    finally:
        db.close()


def clear_item_override(run_id: int, socket_number: int) -> None:
    db = RunHistoryDb(settings.run_history_db_path)
    try:
        db.clear_item_override(int(run_id), int(socket_number))
        _rebuild_after_edit(db)
    finally:
        db.close()
