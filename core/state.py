from __future__ import annotations

from typing import Dict, Iterable, List, Any, Optional

from .events import Event


class RunState:
    def __init__(self) -> None:
        self.in_run: bool = False

        # instance_id -> template_id (GUID)
        self.instance_map: Dict[str, str] = {}

        # last seen player board snapshot during this run
        self.last_player_board: Optional[List[Dict[str, Any]]] = None

    def handle(self, ev: Event) -> Iterable[Event]:
        # always pass through
        yield ev

        if ev.type == "RunStart":
            self.in_run = True
            self.last_player_board = None
            return

        # Auto-enter run if we see meaningful run events
        if not self.in_run and ev.type in ("ItemPurchased", "BoardState"):
            self.in_run = True

        if ev.type == "ItemPurchased" and ev.instance_id and ev.template_id:
            self.instance_map[ev.instance_id] = ev.template_id
            return

        if ev.type == "BoardState" and ev.board_items:
            # Keep the most recent snapshot
            self.last_player_board = ev.board_items
            return

        if ev.type == "RunEnd":
            self.in_run = False

            # Emit final snapshot of board (sorted by socket)
            if self.last_player_board:
                sorted_items = sorted(self.last_player_board, key=lambda x: x.get("socket_number", 999))
                yield Event(
                    type="FinalBoardSnapshot",
                    raw=ev.raw,
                    board_items=sorted_items,
                    method="last_seen_gamesimhandler_snapshot",
                    confidence=1.0,
                )

            self.in_run = False
            self.last_player_board = None
            return
