"""Row-name matching — the one place that decides whether a source's issuer is a row already on the
board or a genuinely new one.

Row `name`s are keys: the viewer's stars, applications and lot bookkeeping, and every research sheet,
key off them. So the rules are asymmetric. Matching an existing row must be generous (sources spell
issuers differently); creating a new row must be the last resort; and nothing here ever renames.

Order, first hit wins:
  1. exact
  2. `data/aliases.json` — {"source spelling": "board name"}; the human override, always trusted
  3. same exchange symbol as an existing row
  4. equal after normalisation — also tried against the text inside and outside a row's parentheses,
     so "NSE (National Stock Exchange of India)" is found by "National Stock Exchange of India Limited"
  5. one normalised name is a prefix of the other (>= 8 chars)
  6. rapidfuzz token_sort_ratio >= 90, only when unambiguous, always logged. Not token_set_ratio: it
     scores 100 whenever one name's words are a subset of the other's ("Coal India" inside "Bharat
     Coking Coal India"), which is exactly the false match that must never happen.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re

from rapidfuzz import fuzz

log = logging.getLogger("collector.names")

FUZZY_MIN = 90
_STRIP = re.compile(r"\b(limited|ltd|pvt|private|ipo|the|india)\b|[^a-z0-9 ]+")
_SUFFIX = re.compile(r"[\s,]+(?:private\s+|pvt\.?\s+)?(?:limited|ltd\.?)\s*$", re.I)
_PARENS = re.compile(r"\(([^)]*)\)")


def norm_name(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = _STRIP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def display_name(source_name: str) -> str:
    """House spelling for a row that is genuinely new: the source's name without the legal suffix
    ("Hero Motors Limited" -> "Hero Motors"). Applied once, at creation; the name is frozen after."""
    s = re.sub(r"\s+", " ", source_name or "").strip()
    return _SUFFIX.sub("", s).strip() or s


def _forms(name: str) -> set[str]:
    """Normalised forms a row can be recognised by: the whole name, and the text inside / outside
    any parentheses when long enough to be a name rather than a qualifier like "(India)"."""
    forms = {norm_name(name)}
    inner = [norm_name(m) for m in _PARENS.findall(name or "")]
    outer = norm_name(_PARENS.sub(" ", name or ""))
    forms.update(f for f in inner + [outer] if len(f) >= 12)
    forms.discard("")
    return forms


def load_aliases(data_dir: str | pathlib.Path | None) -> dict[str, str]:
    if not data_dir:
        return {}
    p = pathlib.Path(data_dir) / "aliases.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text())
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and not k.startswith("_")}


class Matcher:
    def __init__(self, rows: list[dict], aliases: dict[str, str] | None = None):
        self.names = [r["name"] for r in rows if isinstance(r, dict) and r.get("name")]
        self._set = set(self.names)
        self.aliases = dict(aliases or {})
        self._alias_norm = {norm_name(k): v for k, v in self.aliases.items()}
        self._by_symbol = {str(r["symbol"]).upper(): r["name"] for r in rows
                           if isinstance(r, dict) and r.get("name") and r.get("symbol")}
        self._by_form: dict[str, str] = {}
        for n in self.names:
            for f in _forms(n):
                self._by_form.setdefault(f, n)

    def match(self, name: str, symbol: str | None = None) -> str | None:
        """The existing board spelling for `name`, or None when it is genuinely new."""
        if name in self._set:
            return name
        n = norm_name(name)
        target = self.aliases.get(name) or self._alias_norm.get(n)
        if target:
            return target                     # an alias may name a row not on the board yet: still the name to use
        if symbol and str(symbol).upper() in self._by_symbol:
            return self._by_symbol[str(symbol).upper()]
        if not n:
            return None
        for f in _forms(name):
            if f in self._by_form:
                return self._by_form[f]
        for f, e in self._by_form.items():
            if len(n) >= 8 and len(f) >= 8 and (n.startswith(f) or f.startswith(n)):
                return e
        scored = sorted(((fuzz.token_sort_ratio(n, f), e) for f, e in self._by_form.items()), reverse=True)
        hits = list(dict.fromkeys(e for s, e in scored if s >= FUZZY_MIN))
        if len(hits) == 1:
            log.warning("fuzzy name match %r -> %r (%.0f) — add to data/aliases.json if right, fix if wrong",
                        name, hits[0], scored[0][0])
            return hits[0]
        if len(hits) > 1:
            log.warning("ambiguous fuzzy match for %r: %s — refusing; treated as new", name, hits[:3])
        return None
