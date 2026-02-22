from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class Event:
    type: str
    raw: str

    # GUID in your logs (not int)
    template_id: Optional[str] = None

    # instance ids: itm_..., enc_..., ste_...
    instance_id: Optional[str] = None

    zone: Optional[str] = None
    socket: Optional[str] = None
    size: Optional[str] = None

    method: Optional[str] = None
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}
