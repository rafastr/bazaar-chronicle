import argparse
import time
import datetime

from core.config import settings
from core.tailer import follow_file_lines, replay_file_lines
from core.parser import LogParser
from core.state import RunState
from core.sinks import StdoutSink, ScreenshotSink
from core.instance_store import InstanceStore
from core.run_history_db import RunHistoryDb
from core.run_history_sink import RunHistorySink
from core.run_meta_store import RunMetaStore
from core.run_viewer import list_runs, get_run_board, get_last_run_id, search_templates


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bazaar Chronicle (log-based)")
    p.add_argument(
        "--log",
        dest="log_path",
        default=settings.log_path,
        help="Path to the Unity Player.log (or a local test log)",
    )
    p.add_argument(
        "--replay",
        action="store_true",
        help="Replay the entire log file from start to end (no polling). Useful for testing.",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON events",
    )
    p.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Disable screenshots (recommended on Linux)",
    )
    p.add_argument(
        "--list-runs",
        action="store_true",
        help="List recent stored runs"
    )
    p.add_argument(
        "--show-run",
        type=int,
        help="Show a stored run by run_id (resolved with templates DB)"
    )
    p.add_argument(
        "--last-run",
        action="store_true",
        help="Show the most recent stored run",
    )
    p.add_argument("--confirm-run", type=int, help="Mark a run as confirmed")
    p.add_argument("--set-hero", nargs=2, metavar=("RUN_ID", "HERO"), help="Override hero for a run")
    p.add_argument("--set-rank", nargs=2, metavar=("RUN_ID", "RANK"), help="Override rank for a run")
    p.add_argument("--note-run", nargs=2, metavar=("RUN_ID", "TEXT"), help="Set notes for a run")
    p.add_argument("--set-item", nargs=3, metavar=("RUN_ID", "SOCKET", "TEMPLATE_ID"), help="Override item in a socket")
    p.add_argument("--clear-item", nargs=2, metavar=("RUN_ID", "SOCKET"), help="Clear socket override")
    p.add_argument("--search-template", metavar="QUERY", help="Search templates by name substring")

    return p.parse_args()


def print_run(run: dict) -> None:
    ts = datetime.datetime.fromtimestamp(run["ended_at_unix"])
    print(f'Run {run["run_id"]} ended_at={ts}')

    hero = run.get("hero_effective") or "(unknown)"
    rank = run.get("rank_effective")
    rank_s = str(rank) if rank is not None else "(unknown)"
    confirmed = run.get("is_confirmed", 0)
    print(f"Hero: {hero}")
    print(f"Rank: {rank_s}")
    print(f"Confirmed: {bool(confirmed)}")
    if run.get("notes"):
        print(f"Notes: {run['notes']}")
    print(f'Screenshot: {run["screenshot_path"]}')

    print("Board:")

    for it in run["items"]:
        sock = it["socket_number"]
        size = it["size"]
        name = it["name"] or "(unknown template)"
        tid = it["template_id"] or "NULL"
        print(f"  Socket {sock}: {name} | {size} | {tid}")


def _check_socket(sock: int) -> None:
    if sock < 0 or sock > 9:
        raise SystemExit(f"Invalid socket {sock}. Must be 0-9.")


def run_tracker_watch_mode(
    log_path: str | None = None,
    *,
    pretty: bool | None = None,
    screenshots_enabled: bool | None = None,
) -> None:
    """
    Start the normal tracker watch loop.
    Intended for app launcher / packaged builds.
    """
    log_path = log_path or settings.log_path
    pretty = settings.pretty_json if pretty is None else pretty
    screenshots_enabled = settings.enable_screenshots if screenshots_enabled is None else screenshots_enabled

    print("Bazaar Chronicles")
    print("Watching:", log_path)
    print("Mode:", "follow")
    print("Instance cache:", settings.instance_map_path)
    print("Run history DB:", settings.run_history_db_path)

    store = InstanceStore(settings.instance_map_path)
    meta_store = RunMetaStore(settings.run_meta_path)
    run_db = RunHistoryDb(settings.run_history_db_path)

    parser = LogParser()
    state = RunState(store=store, meta_store=meta_store)

    screenshot_sink = ScreenshotSink(
        enabled=screenshots_enabled,
        out_dir=settings.screenshot_dir,
        monitor_index=settings.screenshot_monitor_index,
        delay_seconds=settings.screenshot_delay_seconds,
        cooldown_seconds=settings.screenshot_cooldown_seconds,
        trigger_event_types=set(settings.screenshot_trigger_event_types or []),
    )

    sinks = [
        StdoutSink(pretty=pretty),
        screenshot_sink,
        RunHistorySink(run_db),
    ]

    line_source = follow_file_lines(
        log_path,
        poll_interval_seconds=settings.poll_interval_seconds,
        encoding=settings.log_encoding,
        errors=settings.log_encoding_errors,
    )

    try:
        for line in line_source:
            ev = parser.parse_line(line)
            if ev is None:
                continue

            if ev.type == "RunEnd":
                emitted = screenshot_sink.handle(ev)
                for e2 in emitted:
                    for out2 in state.handle(e2):
                        for sink in sinks:
                            sink.handle(out2)

            for out_ev in state.handle(ev):
                for sink in sinks:
                    sink.handle(out_ev)

            if settings.loop_sleep_seconds > 0:
                time.sleep(settings.loop_sleep_seconds)

    finally:
        run_db.close()


def main() -> None:
    args = parse_args()

    if args.list_runs:
       rows = list_runs(settings.run_history_db_path, limit=50)
       for r in rows:
           ts = datetime.datetime.fromtimestamp(r["ended_at_unix"])
           hero = r.get("hero_effective") or "(unknown)"
           rank = r.get("rank_effective")
           rank_s = str(rank) if rank is not None else "(unknown)"
           confirmed = bool(r.get("is_confirmed", 0))
           print(
               f'run_id={r["run_id"]} ended_at={ts} hero={hero} rank={rank_s} confirmed={confirmed} screenshot={r["screenshot_path"]}'
           )
       return   

    if args.show_run is not None:
        run = get_run_board(settings.run_history_db_path, settings.templates_db_path, args.show_run)
        print_run(run)
        return

    if args.last_run:
        run_id = get_last_run_id(settings.run_history_db_path)
        if run_id is None:
            print("No runs stored yet.")
            return
    
        run = get_run_board(
            settings.run_history_db_path,
            settings.templates_db_path,
            run_id,
        )
        print_run(run)
        return

    # --- Editing / utility mode ---
    if args.search_template:
        rows = search_templates(settings.templates_db_path, args.search_template, limit=30)
        for r in rows:
            print(f'{r["template_id"]} | {r["name"]} | size={r.get("size")} | art={r.get("art_key")}')
        return
    
    # For write operations, open run DB
    if any([args.confirm_run, args.set_hero, args.set_rank, args.note_run, args.set_item, args.clear_item]):
        db = RunHistoryDb(settings.run_history_db_path)
        try:
            if args.confirm_run is not None:
                db.confirm_run(int(args.confirm_run), confirmed=True)
                print({"type": "RunConfirmed", "run_id": int(args.confirm_run)})
                return
    
            if args.set_hero:
                run_id = int(args.set_hero[0])
                hero = args.set_hero[1]
                db.set_run_hero_override(run_id, hero)
                print({"type": "RunHeroOverrideSet", "run_id": run_id, "hero": hero})
                return
    
            if args.set_rank:
                run_id = int(args.set_rank[0])
                rank = int(args.set_rank[1])
                db.set_run_rank_override(run_id, rank)
                print({"type": "RunRankOverrideSet", "run_id": run_id, "rank": rank})
                return
    
            if args.note_run:
                run_id = int(args.note_run[0])
                text = args.note_run[1]
                db.set_run_notes(run_id, text)
                print({"type": "RunNotesSet", "run_id": run_id})
                return
    
            if args.set_item:
                run_id = int(args.set_item[0])
                socket = int(args.set_item[1])
                _check_socket(socket)
                template_id = args.set_item[2]
                db.upsert_item_override(run_id, socket_number=socket, template_id_override=template_id)
                print({"type": "RunItemOverrideSet", "run_id": run_id, "socket": socket, "template_id": template_id})
                return
    
            if args.clear_item:
                run_id = int(args.clear_item[0])
                socket = int(args.clear_item[1])
                _check_socket(socket)
                db.clear_item_override(run_id, socket)
                print({"type": "RunItemOverrideCleared", "run_id": run_id, "socket": socket})
                return
        finally:
            db.close()
    
    run_tracker_watch_mode(
        log_path=args.log_path,
        pretty=args.pretty or settings.pretty_json,
        screenshots_enabled=settings.enable_screenshots and (not args.no_screenshots),
    )
    

if __name__ == "__main__":
    main()
