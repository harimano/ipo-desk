"""logos — owns `logos`; writes one small thumbnail per issue to `logos/<igId>.webp` beside latest.json.

InvestorGain's per-issue record names a logo file (`details` copies it onto the row as `logo`); the image itself is served
from chittorgarh.net/images/ipo/<file>, a PNG of ~100 KB. Hotlinking that would cost a viewer ~3 MB a board, so each one
is fetched ONCE, shrunk to a 96 x 48 WebP (~0.5-3 KB) and published with the site. The page asks only for logos this
map lists, so it never requests a missing image.

  logos[igId] = {src, at}                  a thumbnail exists at logos/<igId>.webp, made from `src` on date `at`
  logos[igId] = {src, at, missing: true}   the source answered without an image; tried again after RETRY_DAYS

Rows are the board's (mainboard, sme) and `recent`. At most PER_RUN downloads a run, newest issues first. A logo that
fails to download or decode costs that logo and nothing else; the module fails only when every attempt failed.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceError
from ..http import Session
from ..result import Result

log = logging.getLogger("collector.logos")
IST = ZoneInfo("Asia/Kolkata")
SRC = "logos"
BASE = "https://www.chittorgarh.net/images/ipo/"
SIZE = (96, 48)            # 2:1 — most IPO logos are wordmarks; a square shrinks them to a strip
PER_RUN = 25
RETRY_DAYS = 7
MAX_SOURCE_BYTES = 3 * 1024 * 1024


def thumbnail(raw: bytes) -> bytes:
    """Any image -> a SIZE WebP, the logo centred on transparency, aspect kept. Raises SourceChanged on a non-image."""
    from PIL import Image, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError) as e:
        raise SourceChanged(SRC, f"not an image ({type(e).__name__})")
    im = im.convert("RGBA")
    box = im.getbbox()                       # trim transparent margins so small marks are not lost in padding
    if box:
        im = im.crop(box)
    im.thumbnail(SIZE, Image.LANCZOS)
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.paste(im, ((SIZE[0] - im.width) // 2, (SIZE[1] - im.height) // 2), im)
    out = io.BytesIO()
    canvas.save(out, "WEBP", quality=82, method=6)
    return out.getvalue()


def wanted(doc: dict, have: dict, today: dt.date) -> list[tuple[str, str]]:
    """[(igId, logo file)] still to fetch, newest listing / opening first."""
    rows = [r for k in ("mainboard", "sme", "recent") for r in (doc.get(k) or []) if isinstance(r, dict)]
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: str(r.get("open") or r.get("listingDate") or ""), reverse=True):
        ig, src = str(r.get("igId") or ""), str(r.get("logo") or "").strip()
        if not ig or not src or ig in seen:
            continue
        seen.add(ig)
        h = have.get(ig) or {}
        if h.get("src") == src and not h.get("missing"):
            continue
        if h.get("missing") and h.get("src") == src:
            try:
                if (today - dt.date.fromisoformat(h.get("at", "")[:10])).days < RETRY_DAYS:
                    continue
            except ValueError:
                pass
        out.append((ig, src))
    return out


def run(session: Session, prev: dict, res: Result) -> Result:
    today = dt.datetime.now(IST).date()
    have = {k: dict(v) for k, v in (prev.get("logos") or {}).items() if isinstance(v, dict)}
    todo = wanted(res.doc or prev, have, today)
    if not todo:
        res.notes.append(f"{sum(1 for v in have.values() if not v.get('missing'))} logos on file; none to fetch")
        return res.won("none", today.isoformat())
    made, missing, errors = 0, 0, []
    for ig, src in todo[:PER_RUN]:
        url = BASE + src
        try:
            raw = session.get_bytes(url, source=SRC)
            if len(raw) > MAX_SOURCE_BYTES:
                raise SourceChanged(SRC, f"{len(raw)} B is not a logo", url)
            res.files[f"logos/{ig}.webp"] = thumbnail(raw)
            have[ig] = {"src": src, "at": today.isoformat()}
            made += 1
        except SourceChanged as e:
            have[ig] = {"src": src, "at": today.isoformat(), "missing": True}
            missing += 1
            log.info("logo %s: %s", ig, e.detail)
        except SourceError as e:
            if getattr(e, "status", None) == 404:
                have[ig] = {"src": src, "at": today.isoformat(), "missing": True}
                missing += 1
            else:
                errors.append(f"{ig}: {e.kind}")
    if made == 0 and missing == 0 and errors:
        return res.fail(SourceChanged(SRC, f"no logo fetched: {'; '.join(errors[:3])}"))
    res.replace["logos"] = have
    res.notes.append(f"{made} logos made, {missing} missing, {len(errors)} errors; {len(todo) - min(len(todo), PER_RUN)} left; "
                     f"{sum(1 for v in have.values() if not v.get('missing'))} on file")
    return res.won("chittorgarh.net", today.isoformat())
