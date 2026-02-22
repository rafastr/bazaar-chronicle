from __future__ import annotations

from typing import Dict, Iterable

from .events import Event


class RunState:
    def __init__(self) -> None:
        self.in_run: bool = False

        # persistent in-memory map (later: sqlite)
        self.instance_map: Dict[str, str] = {}  # instance_id -> template_guid

    def handle(self, ev: Event) -> Iterable[Event]:
        yield ev

        if ev.type == "RunStart":
            self.in_run = True
            return

        if ev.type == "RunEnd":
            self.in_run = False
            return

        if not self.in_run:
            return

        # Purchase already gives us direct mapping
        if ev.type == "ItemPurchased" and ev.instance_id and ev.template_id:
            self.instance_map[ev.instance_id] = ev.template_id
            return
