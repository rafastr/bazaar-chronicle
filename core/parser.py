from __future__ import annotations

import re
from typing import Optional

from .events import Event


class LogParser:
    # Known markers from your notes
    RUN_START_MARKER = "[StartRunAppState] Run initialization finalized."
    RUN_END_MARKER = "Starting card reveal sequence"

    # Your current trigger string
    REVEAL_TRIGGER = "Starting card reveal sequence"

    # GUID matcher (canonical 8-4-4-4-12)
    _GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

    # Your exact format:
    # "... Card Purchased: InstanceId: itm_XXXX - TemplateId<GUID> - Target:..."
    _re_item_purchase = re.compile(
        rf"Card Purchased:\s*InstanceId:\s*(?P<iid>itm_[A-Za-z0-9_]+)\s*-\s*TemplateId(?P<tid>{_GUID})\b",
        re.IGNORECASE,
    )

    # (keep your spawn regex etc. for later; not needed for this step)

    def parse_line(self, line: str) -> Optional[Event]:
        raw = line

        if self.RUN_START_MARKER in line:
            return Event(type="RunStart", raw=raw)

        if self.RUN_END_MARKER in line:
            return Event(type="RunEnd", raw=raw)

        if self.REVEAL_TRIGGER in line:
            return Event(type="CardRevealSequenceStart", raw=raw)

        # Item purchases only (itm_*)
        m = self._re_item_purchase.search(line)
        if m:
            return Event(
                type="ItemPurchased",
                raw=raw,
                instance_id=m.group("iid"),
                template_id=m.group("tid"),
            )

        return None
