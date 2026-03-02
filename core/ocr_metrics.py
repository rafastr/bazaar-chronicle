from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Tuple

from PIL import Image, ImageOps
import pytesseract
from core.config import settings

if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

ROI = Tuple[int, int, int, int]


def _normalize_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return p

    # If DB contains Windows backslashes, convert to Linux separator
    p = p.replace("\\", os.sep)

    # If it's relative, interpret relative to project root (cwd)
    if not os.path.isabs(p):
        p = os.path.abspath(p)

    return p


def _prep_digits(
    img: Image.Image,
    *,
    invert: bool = False,
    thresh: int = 180,
    scale: int = 3,
) -> Image.Image:
    """
    Preprocess for digit OCR.
    - grayscale + autocontrast
    - optional upscale
    - threshold to B/W
    - optional invert (useful when UI is light-on-dark)
    """
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)

    if scale and scale > 1:
        g = g.resize((g.width * scale, g.height * scale))

    bw = g.point(lambda p: 255 if p > thresh else 0)

    if invert:
        bw = ImageOps.invert(bw)

    return bw


def _ocr_digits(img: Image.Image, *, psm: int = 7, oem: int = 3) -> str:
    cfg = f"--oem {oem} --psm {psm} -c tessedit_char_whitelist=0123456789"
    return pytesseract.image_to_string(img, config=cfg).strip()


def _parse_int(s: str) -> int | None:
    s = (s or "").replace(",", "").strip()
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _drop_left(img: Image.Image, frac: float) -> Image.Image:
    """
    Drop the left portion of the ROI to reduce icon interference.
    frac is clamped to [0.0, 0.9].
    """
    frac = max(0.0, min(0.9, float(frac)))
    drop = int(img.width * frac)
    if drop <= 0:
        return img
    return img.crop((drop, 0, img.width, img.height))


def _try_read_int(crop: Image.Image) -> tuple[int | None, dict]:
    attempts: list[dict] = []

    # (drop_left_frac, invert, thresh, psm, scale, oem)
    configs = [
        (0.0, False, 180, 7, 3, 3),
        (0.0, True,  180, 7, 3, 3),

        (0.35, False, 180, 7, 3, 3),
        (0.35, True,  180, 7, 3, 3),
        (0.35, False, 160, 7, 3, 3),
        (0.35, True,  200, 7, 3, 3),

        (0.35, False, 180, 8, 3, 3),
        (0.35, False, 180, 6, 3, 3),

        (0.45, False, 180, 7, 3, 3),
        (0.45, True,  180, 7, 3, 3),

        # Extra robustness for tiny/thin digits (often "level")
        (0.35, False, 140, 7, 4, 3),
        (0.35, True,  220, 7, 4, 3),

        # Try LSTM-only engine
        (0.35, False, 180, 7, 3, 1),
        (0.35, True,  180, 7, 3, 1),
    ]

    best_attempt = None
    best_val = None
    best_digits_len = -1

    for drop_frac, inv, thr, psm, scale, oem in configs:
        img2 = _drop_left(crop, drop_frac) if drop_frac else crop
        prep = _prep_digits(img2, invert=inv, thresh=thr, scale=scale)
        raw = _ocr_digits(prep, psm=psm, oem=oem)

        digits = re.findall(r"\d+", (raw or "").replace(",", ""))
        digits_join = "".join(digits)
        val = int(digits_join) if digits_join else None

        attempt = {
            "drop_left": drop_frac,
            "invert": inv,
            "thresh": thr,
            "psm": psm,
            "scale": scale,
            "oem": oem,
            "raw": raw,
            "digits": digits_join,
            "value": val,
        }
        attempts.append(attempt)

        if val is None:
            continue

        # Prefer the attempt with more digits (more stable), tie-break by larger value
        if len(digits_join) > best_digits_len:
            best_digits_len = len(digits_join)
            best_val = val
            best_attempt = attempt
        elif len(digits_join) == best_digits_len and best_val is not None and val > best_val:
            best_val = val
            best_attempt = attempt

    return best_val, {"best": best_attempt, "attempts": attempts}


def extract_run_metrics(
    screenshot_path: str,
    rois_for_resolution: Dict[str, Any],
    debug_dir: str | None = None,
    ocr_version: str = "v1",
) -> Dict[str, Any]:
    """
    Returns:
      {
        "wins": int|None,
        "max_health": int|None,
        "prestige": int|None,
        "level": int|None,
        "income": int|None,
        "gold": int|None,
        "won": bool,
        "ocr_json": str,
        "ocr_version": str,
        "updated_at_unix": int
      }
    """
    screenshot_path = _normalize_path(screenshot_path)
    if not os.path.exists(screenshot_path):
        raise FileNotFoundError(f"Screenshot not found: {screenshot_path}")

    im = Image.open(screenshot_path)
    w, h = im.size
    key = f"{w}x{h}"

    if key not in rois_for_resolution:
        raise RuntimeError(f"No OCR ROIs for resolution {key}. Add it to core/ocr_rois.py")

    rois = rois_for_resolution[key]

    debug: Dict[str, Any] = {"resolution": key, "fields": {}}
    out: Dict[str, Any] = {}

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    for field, roi in rois.items():
        x, y, rw, rh = map(int, roi)
        crop = im.crop((x, y, x + rw, y + rh))

        # Save raw crop for debugging
        if debug_dir:
            crop.save(os.path.join(debug_dir, f"{field}_crop.png"))

        val, dbg = _try_read_int(crop)

        # Save the "best" preprocessed image as well (if any attempt existed)
        if debug_dir and dbg.get("best"):
            best = dbg["best"]
            img2 = _drop_left(crop, best["drop_left"]) if best["drop_left"] else crop
            prep_best = _prep_digits(
                img2,
                invert=bool(best["invert"]),
                thresh=int(best["thresh"]),
                scale=int(best["scale"]),
            )
            prep_best.save(os.path.join(debug_dir, f"{field}_prep_best.png"))

        out[field] = val
        debug["fields"][field] = {"roi": [x, y, rw, rh], **dbg}

    wins = out.get("wins")
    out["won"] = bool(wins is not None and wins >= 10)

    out["ocr_json"] = json.dumps(debug, ensure_ascii=False)
    out["ocr_version"] = ocr_version
    out["updated_at_unix"] = int(time.time())
    return out
