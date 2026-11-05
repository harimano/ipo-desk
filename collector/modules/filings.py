"""filings — the quota radar. Row patcher for `quota`: stage, bucket, stageDate, recordDate,
listingDate, isNew, needsReview ONLY. It never writes quota / quotaPct / confidence / sources:
those come from data/quota-reviews/ (a human reading of the reservation clause) via the assembler.

What it does each run:
  (a) builds the parent watchlist from prev["quota"] rows (ticker + parentFull) joined to the BSE
      scrip-code map in collector/sources/parents.json;
  (b) polls BSE corporate announcements for each parent over the last 3 days and, for a headline
      matching HEADLINE_RE, advances the row (DRHP filed -> bucket drhp; observation letter -> approved;
      RHP -> approved, stage "RHP filed") and sets needsReview {source, url, headline, date};
  (c) diffs page 1 of SEBI's DRHP and RHP registers against prev to catch filings the parent did
      not announce, matching subsidiary names to quota row names after normalisation;
  (d) moves rows whose listingDate is now past to bucket done;
  (e) discovery: reads NSE's market-wide announcements (last 4 days, both boards) for a listed company
      speaking about a subsidiary's offer. Those are `quotaLeads[]` (60 days). A lead from a watched parent
      moves its quota row as (b) would (BSE is blocked on the runners); a lead naming an `expected` row, and
      an `auto` row whose first word is a listed group's first word, get `quotaCandidate`. A flag, never a
      quota: promotion stays a person reading the DRHP (data/quota-reviews/ + parents.json). A lead that names
      a register issuer (an `expected` row the SEBI registers put there) from a listed announcer is the
      register-to-announcement join: the candidate carries the announcement AND the register row (`register`).
      On the quota rows themselves the join lands on `needsReview` (`register` + `announcement`) when the register
      lists the issuer and the row's own parent announced it (join_quota_evidence).
  (f) reconcile: a quota row whose IPO is on the board or in this year's listings moves to done / gets its
      listingDate (strict name tiers only) and, once the board row has an `igId`, carries it (`quota[].igId`),
      so later runs never depend on spelling;
  (g) the board's own word: `details` writes `shareholderQuota` on every board row from the InvestorGain record
      ({flag, offered, bidLimit, discount, discountPct, parentId, parent, src, at}; None until the record is read).
      Every row with flag true, and every row whose BOOK has a shareholder category while the record says none,
      becomes a `quotaFound[]` entry: the reservation as published, the matched quota row (`quotaRow`, null = NOT
      on the quota list — the discovery), both witnesses (`witness.record`, `witness.book`), the parent's NSE
      symbol when the parent's NAME resolves through the strict tiers against NSE's equity lists (never fuzzy;
      else the matched quota row's hand-written ticker; else null), first seen / last confirmed. Merged with
      yesterday's by igId; an entry leaves SETTLE_DAYS after listing, when the record's flag turns false, or a
      week after its row left the board unlisted. A flag, never a planner row (rule 3): scripts/audit.py turns
      the four disagreements into /admin warnings.
  (h) the parent from the parent's own word: the record never names the parent (prose only) and a reservation the
      quota list does not know has no hand-written ticker, so a `quotaFound` entry with no parent is read against
      `quotaLeads[]`. A lead whose text names the board row — the row's STRICT forms (same name, alias, bracketed
      form; collector/names.py strict_forms) as a whole company name in the sentence, not inside a longer one
      ("South Eastern Coalfields" never gives Eastern Coalfields a parent) — writes the announcer as parent /
      parentSymbol with `parentSrc: "nse_ann"` and the announcement under `witness.announcement`. One announcer
      only (two different ones: refused); the announcer is never the issue itself; nothing is promoted to a quota
      row from it. `parentSrc` says where every parent symbol came from: "ig" (the record), "quota" (the matched
      row's ticker), "nse_ann", or null.

bse_ann, sebi and nse_ann are attempted every run; the module is ok if ANY answered, and res.notes
records which. A row nothing mentioned keeps its previous stage (no patch). Stages never regress:
a DRHP headline for a row already approved only flags needsReview.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import re
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceError
from ..http import Session
from ..names import Matcher, display_name, load_aliases, norm_name, strict_forms
from ..result import Result
from ..sources import bse_ann, nse_ann, nse_symbols, sebi

log = logging.getLogger("collector.filings")
IST = ZoneInfo("Asia/Kolkata")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
PARENTS_FILE = pathlib.Path(__file__).resolve().parent.parent / "sources" / "parents.json"

LOOKBACK_DAYS = 3
NEW_FOR_DAYS = 14
ALLOWED_FIELDS = {"stage", "bucket", "stageDate", "recordDate", "listingDate", "isNew", "needsReview", "igId"}
FORBIDDEN_FIELDS = {"quota", "quotaPct", "confidence", "sources"}

HEADLINE_RE = re.compile(
    r"draft red herring|DRHP|red herring|RHP|initial public offer|IPO of .*subsidiary|observation letter", re.IGNORECASE)
_OBS_RE = re.compile(r"observation\s+letter|final\s+observations?", re.IGNORECASE)
_DRHP_RE = re.compile(r"draft\s+red\s+herring|\bU?DRHP\b", re.IGNORECASE)
_RHP_RE = re.compile(r"red\s+herring|\bRHP\b", re.IGNORECASE)
_UPDATED_DRHP_RE = re.compile(r"updated\s+draft|\bUDRHP\b|addendum|corrigendum", re.IGNORECASE)

# bucket rank: a transition may only move a row forward
RANK = {"dropped": -1, "awaited": 0, "drhp": 1, "approved": 2, "done": 3}
_DROP_WORDS = re.compile(
    r"\b(limited|ltd|ipo|drhp|rhp|red|herring|prospectus|draft|dated|private|pvt|updated|udrhp|"
    r"filed|filing|the|of|by|and|for|with|its|intimation|subsidiary)\b")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def normalise(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    s = _DROP_WORDS.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def classify_headline(headline: str) -> dict | None:
    """Map a BSE/SEBI headline to a stage transition.
    Returns {"stage", "bucket", "kind"} or None when the headline is not about a filing.
    kind "generic" (IPO mentioned, no document named) carries stage/bucket None: flag only."""
    if not headline or not HEADLINE_RE.search(headline):
        return None
    if _OBS_RE.search(headline):
        return {"stage": "SEBI observations received", "bucket": "approved", "kind": "observation"}
    if _DRHP_RE.search(headline):
        if _UPDATED_DRHP_RE.search(headline):
            return {"stage": "UDRHP filed", "bucket": "drhp", "kind": "udrhp"}
        return {"stage": "DRHP filed", "bucket": "drhp", "kind": "drhp"}
    if _RHP_RE.search(headline):
        return {"stage": "RHP filed", "bucket": "approved", "kind": "rhp"}
    return {"stage": None, "bucket": None, "kind": "generic"}


def load_parents(path: pathlib.Path = PARENTS_FILE) -> dict[str, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("parents.json unreadable (%s); BSE polling has no scrip codes", e)
        return {}
    return {k.upper(): v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict) and v.get("scrip")}


def watchlist(prev: dict, parents: dict[str, dict]) -> dict[str, dict]:
    """ticker -> {scrip, name, rows: [quota rows]}. Rows with a ticker we have no scrip for are
    still listed (scrip None) so SEBI matching covers them."""
    out: dict[str, dict] = {}
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        t = (row.get("ticker") or "").upper().strip()
        if not t:
            continue
        p = parents.get(t, {})
        entry = out.setdefault(t, {"scrip": p.get("scrip"), "name": row.get("parentFull") or p.get("name"), "rows": []})
        entry["rows"].append(row)
    return out


def _today() -> dt.date:
    return dt.datetime.now(IST).date()


def _transition(row: dict, cls: dict, evidence: dict, patches: dict, today: dt.date) -> bool:
    """Apply a classified filing to a row. Returns True when stage/bucket actually changed."""
    name = row["name"]
    prev_review = row.get("needsReview") or {}
    if evidence.get("url") and prev_review.get("url") == evidence.get("url"):
        return False                       # seen on an earlier run; do not re-stamp or re-flag
    patch = patches.setdefault(name, {})
    if patch.get("needsReview") and (patch["needsReview"].get("date") or "") > (evidence.get("date") or ""):
        return False                       # a newer filing already flagged this row in this run
    patch["needsReview"] = evidence
    if cls.get("kind") == "generic" or not cls.get("bucket"):
        return False
    cur_bucket = patch.get("bucket") or row.get("bucket") or "awaited"
    cur_rank = RANK.get(cur_bucket, 0)
    new_rank = RANK.get(cls["bucket"], 0)
    if cur_bucket == "done":
        return False
    if new_rank < cur_rank:
        return False                       # never regress; needsReview already set
    if new_rank == cur_rank and (patch.get("stage") or row.get("stage")) == cls["stage"]:
        return False                       # same stage already
    patch["stage"] = cls["stage"]
    patch["bucket"] = cls["bucket"]
    patch["stageDate"] = evidence.get("date") or today.isoformat()
    patch["isNew"] = True
    return True


# ---------------------------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------------------------
def _from_bse(session: Session, wl: dict[str, dict], patches: dict, res: Result, today: dt.date) -> str | None:
    polled, answered, hits, errors = 0, 0, 0, []
    since = today - dt.timedelta(days=LOOKBACK_DAYS)
    for ticker, p in wl.items():
        if not p.get("scrip"):
            continue
        polled += 1
        try:
            rows = bse_ann.fetch(session, p["scrip"], since, today, source="bse_ann")
        except SourceError as e:
            errors.append(f"{ticker}: {e.detail}")
            continue
        answered += 1
        rows = [r for r in rows if HEADLINE_RE.search(r["headline"]) or HEADLINE_RE.search(r.get("subject") or "")]
        rows.sort(key=lambda r: (r.get("date") or ""), reverse=True)
        for ann in rows:
            cls = classify_headline(ann["headline"]) or classify_headline(ann.get("subject") or "")
            if not cls:
                continue
            evidence = {"source": "bse_ann", "url": ann.get("url"), "headline": ann["headline"], "date": ann.get("date")}
            targets = _rows_for_announcement(p["rows"], ann["headline"])
            for row in targets:
                if _transition(row, cls, evidence, patches, today):
                    hits += 1
    if polled == 0:
        raise SourceChanged("bse_ann", "no parent has a BSE scrip code; nothing to poll")
    if answered == 0:
        raise SourceChanged("bse_ann", "no parent answered: " + "; ".join(errors[:3]))
    note = f"bse_ann: {answered}/{polled} parents answered, {hits} stage changes"
    if errors:
        note += f", {len(errors)} errors"
    res.notes.append(note)
    return today.isoformat()


def _rows_for_announcement(rows: list[dict], headline: str) -> list[dict]:
    """A parent's announcement names the subsidiary when it can; match on that, else every row of the
    parent gets the flag (one parent usually has one live candidate)."""
    h = normalise(headline)
    named = [r for r in rows if normalise(r["name"]) and normalise(r["name"]) in h]
    return named or rows


def _from_sebi(session: Session, wl: dict[str, dict], prev: dict, patches: dict, res: Result,
               today: dt.date, seen_rows: list[dict]) -> str | None:
    index: list[tuple[str, dict]] = []
    for p in wl.values():
        for row in p["rows"]:
            key = normalise(row["name"])
            if len(key) >= 4:
                index.append((key, row))
    kinds_ok, matched, listed = [], 0, 0
    errors = []
    for kind in ("DRHP", "RHP"):
        try:
            rows = sebi.fetch_listing(session, kind, 1, source="sebi")
        except SourceError as e:
            errors.append(f"{kind}: {e.detail}")
            continue
        kinds_ok.append(kind)
        listed += len(rows)
        seen_rows.extend(rows)
        for f in rows:
            if f.get("kind") == "Addendum":
                continue        # an addendum or corrigendum does not move a stage
            t = normalise(f["title"])
            for key, row in index:
                if key not in t:
                    continue
                reg = f.get("register") or kind           # which SEBI list the row is on is what it means
                cls = {"stage": f"{reg} filed", "bucket": "drhp" if reg == "DRHP" else "approved", "kind": reg.lower()}
                evidence = {"source": "sebi", "url": f["detailUrl"], "headline": f["title"], "date": f.get("date")}
                if _transition(row, cls, evidence, patches, today):
                    matched += 1
    if not kinds_ok:
        raise SourceChanged("sebi", "; ".join(errors) or "no register answered")
    res.notes.append(f"sebi: {'+'.join(kinds_ok)} page 1 ({listed} rows), {matched} stage changes")
    if errors:
        res.notes.append("sebi partial: " + "; ".join(errors))
    return today.isoformat()


# ---------------------------------------------------------------------------------------------
# expected[] — the pipeline beyond the quota names, from the same two SEBI registers
# ---------------------------------------------------------------------------------------------
AUTO_MAX = 30            # machine-added names kept, newest filings first
AUTO_MAX_AGE_DAYS = 365  # a DRHP is valid for about a year after SEBI's observations


def _d(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def build_expected(prev: dict, sebi_rows: list[dict], today: dt.date) -> tuple[list[dict], dict]:
    """Hand-written rows keep every word; the registers only add facts to them.

      * a row now on the board (or in `recent`) has launched: it leaves;
      * a row SEBI lists on the RHP register gets stage "RHP filed <date>";
      * every matched row gets `lastFiling` {register, kind, date, title, url};
      * an issuer on the DRHP register that is nowhere else (expected, board, recent, quota) joins as an
        `auto` row — name, filing date, the SEBI link, nothing invented. Size and window stay null until
        someone reads the document. At most AUTO_MAX of them, none older than AUTO_MAX_AGE_DAYS.
    """
    stats = {"new": 0, "rhp": 0, "launched": 0}
    aliases = load_aliases(ALIASES_DIR)
    elsewhere = Matcher([r for k in ("mainboard", "sme", "recent", "quota") for r in (prev.get(k) or [])
                         if isinstance(r, dict)], aliases)
    rows = []
    for r in prev.get("expected") or []:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        if elsewhere.match(r["name"]):
            stats["launched"] += 1
            continue
        rows.append(dict(r))
    matcher = Matcher(rows, aliases)
    by_name = {r["name"]: r for r in rows}

    filings_ = sorted((f for f in sebi_rows if f.get("issuer") and f.get("date")), key=lambda f: f["date"])
    for f in filings_:                                     # oldest first, so the newest filing has the last word
        name = matcher.match(f["issuer"])
        row = by_name.get(name) if name else None
        if row is None:
            if f.get("register") != "DRHP" or f.get("kind") == "Addendum" or elsewhere.match(f["issuer"]):
                continue                                   # RHP-register names reach the board through calendar
            row = {"name": display_name(f["issuer"]), "window": None, "stage": None, "sizeCr": None, "sizeText": None,
                   "note": None, "parent": None, "sources": [], "auto": True}
            rows.append(row)
            by_name[row["name"]] = row
            matcher = Matcher(rows, aliases)
            stats["new"] += 1
        last = row.get("lastFiling") or {}
        if (last.get("date") or "") <= f["date"]:
            row["lastFiling"] = {"register": f.get("register"), "kind": f.get("kind"), "date": f["date"],
                                 "title": f["title"], "url": f["detailUrl"]}
        if f.get("kind") == "Addendum":
            continue
        when = _d(f["date"])
        label = f"{f['register']} filed {when.day} {when:%b %Y}" if when else f"{f['register']} filed"
        if f.get("register") == "RHP" and not str(row.get("stage") or "").startswith("RHP filed"):
            row["stage"] = label
            stats["rhp"] += 1
        elif row.get("auto") and f.get("register") == "DRHP":
            row["stage"] = label
            row["sizeText"] = f"DRHP {when.day} {when:%b}" if when else "DRHP filed"
        if f["detailUrl"] not in (row.get("sources") or []):
            row["sources"] = ([f["detailUrl"]] + list(row.get("sources") or []))[:4]

    def filed(r):
        return (r.get("lastFiling") or {}).get("date") or ""
    hand = [r for r in rows if not r.get("auto")]
    auto = [r for r in rows if r.get("auto") and (_d(filed(r)) is None or (today - _d(filed(r))).days <= AUTO_MAX_AGE_DAYS)]
    auto.sort(key=filed, reverse=True)
    return hand + auto[:AUTO_MAX], stats


# ---------------------------------------------------------------------------------------------
# discovery — listed parents the quota list does not know yet. It flags; it never asserts a quota.
# ---------------------------------------------------------------------------------------------
ANN_LOOKBACK_DAYS = 4    # two full runs a day; four days covers a weekend and one missed day
LEAD_MAX_DAYS = 60
LEAD_MAX = 40
_ANN_DOC_RE = re.compile(r"red\s+herring|\bU?DRHP\b|initial\s+public\s+offer|\bIPO\b|offer\s+document|prospectus|"
                         r"observation\s+letter", re.IGNORECASE)
# … or a listed company speaking of a reservation for ITS shareholders in that offer (Reliance on Jio Platforms, 16 Oct 2026:
# "Reservation for eligible RIL shareholders" — none of Reliance's seven Jio announcements said "subsidiary")
_ANN_REL_RE = re.compile(r"subsidiar|step[\s-]*down|group\s+compan|associate\s+compan|joint\s+venture|"
                         r"reservation\s+for\s+(?:\S+\s+){0,3}shareholders?\b|shareholders?\s+reservation|shareholders?\s+quota",
                         re.IGNORECASE)
# a company talking about its OWN past offer: proceeds, monitoring agency, anniversaries
_ANN_OWN_RE = re.compile(r"utili[sz]ation|proceeds|monitoring\s+agency|variation|anniversary|milestone|years\s+of\s+(its\s+)?IPO",
                         re.IGNORECASE)
_WITHDRAW_RE = re.compile(r"withdr[ae]w", re.IGNORECASE)

NAME_MAX_SHARED = 15     # a first word more than this many listed companies share is not a group name (Tata: 13)
NAME_STOP = frozenset("""
    india indian bharat hindustan hind indo gujarat maharashtra bombay mumbai delhi bengal punjab rajasthan
    kerala tamil andhra madras karnataka south north east west eastern western southern northern central
    national international global united new modern standard general universal super supreme royal star sun
    premier prime first capital asian orient oriental shree shri sri jai om maa sai ganesh laxmi lakshmi
    krishna balaji mahalaxmi blue green golden silver
""".split())  # noqa: SIM905  a word list reads as prose


def classify_lead(text: str) -> str | None:
    """An NSE announcement's summary -> lead kind, or None when it is not a listed company speaking about a
    subsidiary's (or group company's) offer. Kinds: drhp / udrhp / rhp / observation / withdrawn / ipo."""
    if not text or not _ANN_DOC_RE.search(text) or not _ANN_REL_RE.search(text) or _ANN_OWN_RE.search(text):
        return None
    if _WITHDRAW_RE.search(text):
        return "withdrawn"
    cls = classify_headline(text)
    return cls["kind"] if cls and cls["kind"] != "generic" else "ipo"


def _from_nse_ann(session: Session, today: dt.date, found: list[dict], res: Result) -> str | None:
    since = today - dt.timedelta(days=ANN_LOOKBACK_DAYS)
    scanned = 0
    for index in ("equities", "sme"):
        try:
            rows = nse_ann.fetch(session, index, since, today, source="nse_ann")
        except SourceError as e:
            if index == "equities":
                raise                          # the mainboard list is the leg; an empty SME window is ordinary
            res.notes.append(f"nse_ann sme: {e.detail}")
            continue
        scanned += len(rows)
        for a in rows:
            kind = classify_lead(a["text"])
            if kind and a.get("symbol"):
                found.append({"parentSymbol": a["symbol"], "parentName": a.get("company"), "kind": kind,
                              "text": a["text"][:300], "url": a.get("url"), "date": a.get("date"),
                              "seqId": a.get("seqId"), "sme": index == "sme"})
    res.notes.append(f"discover: {scanned} announcements scanned, {len(found)} subsidiary-offer leads")
    return today.isoformat()


def _lead_key(lead: dict) -> str:
    return lead.get("seqId") or f"{lead.get('parentSymbol')}|{lead.get('date')}|{lead.get('text', '')[:60]}"


def merge_leads(prev_leads: list[dict], found: list[dict], today: dt.date) -> list[dict]:
    """Yesterday's leads plus today's, one per announcement, newest first, none older than LEAD_MAX_DAYS."""
    by: dict[str, dict] = {}
    for lead in list(prev_leads or []) + found:
        if isinstance(lead, dict) and lead.get("parentSymbol"):
            by[_lead_key(lead)] = {**by.get(_lead_key(lead), {}), **lead}
    keep = [x for x in by.values() if _d(x.get("date")) is None or (today - _d(x["date"])).days <= LEAD_MAX_DAYS]
    keep.sort(key=lambda x: x.get("date") or "", reverse=True)
    return keep[:LEAD_MAX]


def _row_key(name: str) -> str | None:
    """A row name specific enough to find inside an announcement: two words, or one of 6+ letters."""
    k = normalise(name)
    return k if (len(k.split()) >= 2 or len(k) >= 6) else None


def _leads_to_quota(leads: list[dict], wl: dict[str, dict], patches: dict, today: dt.date) -> int:
    """A lead from a parent already on the quota list moves that row the way a BSE headline would (the BSE
    per-parent poll is blocked on the runners). A withdrawal only flags the row."""
    hits = 0
    for lead in sorted(leads, key=lambda x: x.get("date") or ""):
        p = wl.get(lead["parentSymbol"])
        if not p:
            continue
        lead["watched"] = True
        cls = classify_headline(lead["text"]) if lead["kind"] != "withdrawn" else None
        cls = cls or {"stage": None, "bucket": None, "kind": "generic"}
        evidence = {"source": "nse_ann", "url": lead.get("url"), "headline": lead["text"], "date": lead.get("date")}
        for row in _rows_for_announcement(p["rows"], lead["text"]):
            if _transition(row, cls, evidence, patches, today):
                hits += 1
    return hits


def join_quota_evidence(prev: dict, sebi_rows: list[dict], leads: list[dict], patches: dict) -> int:
    """The register-to-announcement join on the quota rows themselves: when SEBI's register (page 1, this run) lists the
    row's issuer AND a lead from the row's own parent names it, the row's `needsReview` gains `register` {register, kind,
    date, title, url} and `announcement` {parentSymbol, kind, date, url} — two documents, both linked, neither read (5 Nov
    2026: Coal India's lead on South Eastern Coalfields moved the row; the register row behind it was not kept). Only an
    existing needsReview is extended (either source naming the row wrote one); nothing else on the row changes."""
    joined = 0
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name") or row.get("bucket") in ("done", "dropped"):
            continue
        key, ticker = _row_key(row["name"]), str(row.get("ticker") or "").upper().strip()
        if not key or not ticker:
            continue
        regs = sorted((f for f in sebi_rows if f.get("kind") != "Addendum" and f.get("detailUrl")
                       and key in normalise(f.get("title") or "")), key=lambda f: f.get("date") or "")
        anns = sorted((x for x in leads if isinstance(x, dict) and x.get("kind") != "withdrawn" and x.get("url")
                       and str(x.get("parentSymbol") or "").upper() == ticker and key in normalise(x.get("text") or "")),
                      key=lambda x: x.get("date") or "")
        if not regs or not anns:
            continue
        review = dict(patches.get(row["name"], {}).get("needsReview") or row.get("needsReview") or {})
        if not review:
            continue
        reg, ann = regs[-1], anns[-1]
        add = {"register": {"register": reg.get("register"), "kind": reg.get("kind"), "date": reg.get("date"),
                            "title": reg.get("title"), "url": reg["detailUrl"]},
               "announcement": {"parentSymbol": ann["parentSymbol"], "kind": ann.get("kind"), "date": ann.get("date"), "url": ann["url"]}}
        if review.get("register") == add["register"] and review.get("announcement") == add["announcement"]:
            continue
        patches.setdefault(row["name"], {})["needsReview"] = {**review, **add}
        joined += 1
    return joined


def _candidate(lead: dict, company: dict | None = None, register: dict | None = None) -> dict:
    """An announcement candidate. `company` is the announcer's row in NSE's equity list (its listed name);
    `register` is the row's SEBI filing (`lastFiling`) — the join: the register says the issuer filed, the parent's
    announcement says whose subsidiary it is, and both links are kept as the evidence."""
    out = {"via": "announcement", "parents": [{"symbol": lead["parentSymbol"],
                                               "name": (company or {}).get("name") or lead.get("parentName")}],
           "kind": lead["kind"], "text": lead["text"], "url": lead.get("url"), "date": lead.get("date")}
    if register and register.get("url"):
        out["register"] = {k: register.get(k) for k in ("register", "kind", "date", "title", "url")}
    return out


def attach_candidates(expected: list[dict], leads: list[dict], companies: list[dict] | None) -> dict:
    """Mark `expected` rows that may carry a shareholder quota. Adds `quotaCandidate` and nothing else:
      * via "announcement" — a listed company's announcement about a subsidiary's offer names the row.
        The announcer must not be the row itself (listed issuers announce their own business every day) and must
        be a listed symbol (checked against NSE's equity lists when they loaded). A row the SEBI registers put
        there carries its filing too (`register`): the register-to-announcement join.
      * via "name" — an `auto` row's first word is a listed company's first word (a group name). Weak:
        Madhur Iron -> Madhur Knitting is expected. Never replaces an announcement candidate.
    Leads that name a row get `matched` = the row's name."""
    stats = {"announcement": 0, "name": 0}
    keyed = [(k, r) for r in expected if isinstance(r, dict) and r.get("name") and (k := _row_key(r["name"]))]
    listed = {c["symbol"]: c for c in companies or [] if isinstance(c, dict) and c.get("symbol")}
    for lead in sorted(leads, key=lambda x: x.get("date") or ""):   # the newest announcement has the last word
        if lead.get("kind") == "withdrawn":
            continue
        # the announcer must be a listed symbol: NSE's feed carries only listed companies, and when the equity lists
        # loaded the symbol is checked against them (and the listed name carried as evidence)
        company = listed.get(lead["parentSymbol"])
        if companies is not None and listed and company is None:
            continue
        text = normalise(lead["text"])
        parent = normalise(lead.get("parentName") or "")
        for k, row in keyed:
            if k in text and not parent.startswith(k):
                row["quotaCandidate"] = _candidate(lead, company, row.get("lastFiling"))
                lead["matched"] = row["name"]
    firsts: dict[str, list[dict]] = {}
    for c in companies or []:
        words = normalise(c.get("name") or "").split()
        if words:
            firsts.setdefault(words[0], []).append(c)
    for row in expected:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        cand = row.get("quotaCandidate") or {}
        if cand.get("via") == "announcement":
            stats["announcement"] += 1
            continue
        if companies is None:                 # the list did not load: keep whatever name flag was there
            stats["name"] += bool(cand)
            continue
        row.pop("quotaCandidate", None)
        if not row.get("auto"):
            continue
        own = normalise(row["name"])
        words = own.split()
        first = words[0] if words else ""
        if len(first) < 3 or first in NAME_STOP:
            continue
        group = [c for c in firsts.get(first, []) if normalise(c["name"]) != own]
        if group and len(firsts[first]) <= NAME_MAX_SHARED:
            row["quotaCandidate"] = {"via": "name", "parents": [{"symbol": c["symbol"], "name": c["name"]} for c in group]}
            stats["name"] += 1
    return stats


# ---------------------------------------------------------------------------------------------
# quotaFound — the board's own word on shareholder reservations, read against the quota list
# ---------------------------------------------------------------------------------------------
SETTLE_DAYS = 7          # a found issue leaves the list a week after it lists …
FOUND_GONE_DAYS = 7      # … or a week after its row left the board without listing (calendar dropped it)
FOUND_FIELDS = ("igId", "name", "board", "open", "listing", "parentId", "parent", "parentSymbol", "parentSrc", "offered",
                "bidLimit", "discount", "discountPct", "quotaRow", "witness", "first", "last")
# words that can follow or precede a company name in an NSE summary without being part of it, whatever their case
_NAME_CONNECTIVES = frozenset("""
    a an the and of by for in its on to with from which viz namely re m/s i.e subsidiary subsidiaries material
    wholly owned step step-down associate group company's has have had is are was were will shall filed files filing
""".split())  # noqa: SIM905  a word list reads as prose


def _board_rows(doc: dict) -> list[tuple[str, dict]]:
    return [(board, r) for board in ("mainboard", "sme") for r in (doc.get(board) or [])
            if isinstance(r, dict) and r.get("name") and r.get("igId")]


def book_witness(row: dict, today: dt.date) -> bool | None:
    """Does the exchange's (or Narada's) book show a shareholder category? True when `sub.shareholder` exists; False
    when bidding has opened and the book has its categories but no shareholder one; None before bidding opens or
    while the book is still empty (nothing to witness yet)."""
    sub = row.get("sub") or {}
    if "shareholder" in sub:
        return True
    o = _d(row.get("open"))
    if row.get("status") not in ("Open", "Closed", "Listed") or (o and o > today):
        return None
    if not any(sub.get(k) for k in ("qib", "nii", "retail", "total")):
        return None
    return False


def parent_symbol(parent: str | None, symbols: Matcher | None) -> str | None:
    """The NSE symbol of a parent NAMED by the record, through the strict tiers only (the same name, an alias, a
    bracketed form — never prefix or fuzzy: a wrong parent symbol is the one thing that must not happen)."""
    if not parent or symbols is None:
        return None
    hit = symbols.match_strict(parent)
    return symbols.symbol_of(hit) if hit else None


def _is_name_word(tok: str) -> bool:
    """Does this raw token read as part of a company name? Capitalised, not a connective, not punctuation-led."""
    if not tok or not tok[0].isalnum():
        return False
    bare = tok.strip(".,;:()[]'\"-–—").lower()
    return tok[0].isupper() and bare not in _NAME_CONNECTIVES


def _after(toks: list[str], norms: list[str], j: int) -> str:
    """The first token after position j that could continue a name: legal suffixes (Limited, Ltd, India — tokens
    that normalise to nothing) are stepped over; punctuation, or a suffix closed by punctuation ("Limited,"), ends
    the name and returns ""."""
    for x in range(j + 1, len(toks)):
        t = toks[x]
        if not t[0].isalnum():
            return ""
        if norms[x]:
            return t
        if not t[-1].isalnum():
            return ""
    return ""


def mentions(text: str, forms: set[str]) -> bool:
    """Does the sentence name a company under one of these strict forms — the WHOLE name, not part of a longer one?
    Tokens are compared after norm_name (so Limited / Ltd / India drop out, as in names.py); the token before the
    run and the first token after it must not read as name words: "of South Eastern Coalfields Limited (SECL), a"
    names South Eastern Coalfields and nothing shorter, "Bharat Coking Coal India" never names Coal India, and
    "Reliance Jio Platforms" names neither Jio Platforms nor the alias Reliance Jio."""
    toks = (text or "").split()
    norms = [norm_name(t) for t in toks]
    words = [(i, n) for i, n in enumerate(norms) if n]
    for form in forms:
        fw = form.split()
        if not fw:
            continue
        for k in range(len(words) - len(fw) + 1):
            if [n for _, n in words[k:k + len(fw)]] != fw:
                continue
            i, j = words[k][0], words[k + len(fw) - 1][0]
            left = toks[i - 1] if i > 0 else ""
            left_ok = not left or not toks[i][0].isalnum() or not left[-1].isalnum() or not _is_name_word(left)
            right_ok = not toks[j][-1].isalnum() or not _is_name_word(_after(toks, norms, j))
            if left_ok and right_ok:
                return True
    return False


def parent_from_leads(row_name: str, leads: list[dict], aliases: dict[str, str], listed: dict[str, dict] | None) -> dict | None:
    """The announcer of a lead that names this board row, as {parent, parentSymbol, announcement} — or None. Strict: the
    row's forms as a whole name in the text (mentions), the announcer a listed symbol when the equity lists loaded and
    never the issue itself, exactly one announcer across every lead that names the row (two: refused, nothing guessed).
    The newest such announcement is the witness."""
    forms = strict_forms(row_name, aliases)
    if not forms:
        return None
    by_sym: dict[str, dict] = {}
    for lead in sorted((x for x in leads or [] if isinstance(x, dict)), key=lambda x: x.get("date") or ""):
        sym = str(lead.get("parentSymbol") or "").upper().strip()
        if not sym or lead.get("kind") == "withdrawn":
            continue
        company = (listed or {}).get(sym)
        if listed and company is None:
            continue                                          # not a listed symbol: not a parent
        announcer = (company or {}).get("name") or lead.get("parentName") or ""
        if norm_name(announcer) in forms:
            continue                                          # a company on its own offer is not its parent
        if mentions(lead.get("text") or "", forms):
            by_sym[sym] = {"parent": announcer or None, "parentSymbol": sym,
                           "announcement": {"parentSymbol": sym, "kind": lead.get("kind"), "date": lead.get("date"),
                                            "url": lead.get("url")}}
    if len(by_sym) != 1:
        if len(by_sym) > 1:
            log.warning("quotaFound: %r is named by %d different announcers %s — no parent written", row_name, len(by_sym), sorted(by_sym))
        return None
    return next(iter(by_sym.values()))


def discover(prev: dict, doc: dict, patches: dict, companies: list[dict] | None, today: dt.date,
             leads: list[dict] | None = None) -> tuple[dict, dict]:
    """Every board row with an id, read against the quota list: {igId: quotaFound entry} for the rows whose record
    shows a shareholder reservation (witness.record true) or whose book shows a shareholder category the record does
    not (record false, book true). A board row that strictly matches a quota row with no `igId` yet links it
    (patches[name]["igId"]), whatever the record says, so the audit can read record and row side by side."""
    quota = [q for q in prev.get("quota") or [] if isinstance(q, dict) and q.get("name")]
    by_igid = {str(q["igId"]): q for q in quota if q.get("igId")}
    aliases = load_aliases(ALIASES_DIR)
    rows = _board_rows(doc)
    board_ig = {r["name"]: str(r["igId"]) for _, r in rows}
    matcher = Matcher([r for _, r in rows], aliases)          # quota spelling -> board spelling, as _reconcile and the audit
    for q in quota:                                           # link: a quota row with no igId yet, strictly matched
        if q.get("igId"):
            continue
        hit = matcher.match_strict(q["name"])
        ig = board_ig.get(hit) if hit else None               # an alias target may not be on the board: .get
        if ig and ig not in by_igid:                          # never two rows on one issue
            patches.setdefault(q["name"], {})["igId"] = ig
            by_igid[ig] = q
    symbols = Matcher(companies, aliases) if companies else None
    listed = {c["symbol"]: c for c in companies or [] if isinstance(c, dict) and c.get("symbol")} or None
    stats = {"reserved": 0, "unlisted": 0, "disagree": 0, "announced": 0,
             "linked": sum(1 for p in patches.values() if "igId" in p)}
    found: dict[str, dict] = {}
    for board, r in rows:
        ig = str(r["igId"])
        q = by_igid.get(ig)
        shq = r.get("shareholderQuota") if isinstance(r.get("shareholderQuota"), dict) else None
        flag = shq.get("flag") if shq else None
        book = book_witness(r, today)
        if flag is True:
            witness = {"record": True, "book": book}
            stats["reserved"] += 1
        elif flag is False and book is True:
            witness = {"record": False, "book": True}
            stats["disagree"] += 1
        else:
            continue                                          # None: no record yet; false and no book: nothing to say
        parent = (shq or {}).get("parent") or None
        sym, src = parent_symbol(parent, symbols), None
        if sym:
            src = "ig"
        elif q is not None and q.get("ticker"):               # the matched row's hand-written parent ticker
            sym = str(q["ticker"]).upper().strip() or None
            src = "quota" if sym else None
        if flag is True and not sym and not parent:           # (h): the parent's own announcement, strictly matched
            lead = parent_from_leads(r["name"], leads or [], aliases, listed)
            if lead:
                parent, sym, src = lead["parent"], lead["parentSymbol"], "nse_ann"
                witness["announcement"] = lead["announcement"]
                stats["announced"] += 1
        if q is None and flag is True:
            stats["unlisted"] += 1
        found[ig] = {"igId": ig, "name": r["name"], "board": board, "open": r.get("open") or None,
                     "listing": r.get("listing") or None, "parentId": (shq or {}).get("parentId"),
                     "parent": parent, "parentSymbol": sym, "parentSrc": src, "offered": (shq or {}).get("offered"),
                     "bidLimit": (shq or {}).get("bidLimit"), "discount": (shq or {}).get("discount"),
                     "discountPct": (shq or {}).get("discountPct"), "quotaRow": q["name"] if q else None,
                     "witness": witness, "first": today.isoformat(), "last": today.isoformat()}
    return found, stats


def merge_found(prev_found: list[dict], found: dict[str, dict], doc: dict, today: dt.date) -> list[dict]:
    """Yesterday's entries plus today's, one per igId: `first` kept, `last` = today when confirmed, the parent (symbol,
    name, source, announcement) kept when today's lookup could not resolve it (the equity lists are a network call; a
    lead ages out of quotaLeads after LEAD_MAX_DAYS). An entry leaves when its
    issue has settled (listing + SETTLE_DAYS), when its row is on the board and the record now says no reservation
    and the book shows none, or FOUND_GONE_DAYS after its row left the board without listing. An unconfirmed entry
    whose row is on the board (the record not re-read today) is carried as it was."""
    rows = {str(r["igId"]): r for _, r in _board_rows(doc)}
    out: list[dict] = []
    for old in prev_found or []:
        if not isinstance(old, dict) or not old.get("igId"):
            continue
        ig = str(old["igId"])
        if ig in found:
            e = found[ig]
            e["first"] = old.get("first") or e["first"]
            if not e.get("parentSymbol") and old.get("parentSymbol"):
                e["parentSymbol"], e["parentSrc"] = old["parentSymbol"], old.get("parentSrc")
                if not e.get("parent") and old.get("parent"):
                    e["parent"] = old["parent"]
                if old.get("parentSrc") == "nse_ann" and (old.get("witness") or {}).get("announcement"):
                    e["witness"] = {**(e.get("witness") or {}), "announcement": old["witness"]["announcement"]}
            continue
        listing = _d(old.get("listing"))
        if listing and today > listing + dt.timedelta(days=SETTLE_DAYS):
            continue
        r = rows.get(ig)
        if r is not None:
            shq = r.get("shareholderQuota") if isinstance(r.get("shareholderQuota"), dict) else None
            if shq and shq.get("flag") is False and "shareholder" not in (r.get("sub") or {}):
                continue                                      # the record's flag turned false
            out.append({**old, "igId": ig})
            continue
        last = _d(old.get("last"))
        if not listing and last and today > last + dt.timedelta(days=FOUND_GONE_DAYS):
            continue
        out.append({**old, "igId": ig})
    for ig, e in found.items():
        listing = _d(e.get("listing"))
        if listing and today > listing + dt.timedelta(days=SETTLE_DAYS):
            continue
        out.append({k: e.get(k) for k in FOUND_FIELDS})
    out.sort(key=lambda e: (e.get("open") or "9999", e.get("name") or ""))
    return out


def _reconcile(prev: dict, doc: dict, patches: dict, today: dt.date) -> int:
    """A quota row whose IPO is already on the board or in the listings report moves the way a filing would have
    moved it (4 Nov 2026: the hand-written "Reliance Jio" row sat at "SEBI approved — RHP awaited" a week after Jio
    Platforms listed; no filing from the parent said so). Board and listedPerf are TODAY's, assembled earlier in this
    run; names go through the one matcher's STRICT tiers (same name, alias, bracketed form — never prefix or fuzzy:
    "ILJIN Electronics" is not Elin Electronics), so a spelling gap is an aliases.json entry; a listing before this
    year is a different company. Listed -> done with the listing date; on the board but not yet listed ->
    listingDate only, and _expire does the rest after it lists."""
    moved = 0
    board = [r for k in ("mainboard", "sme") for r in (doc.get(k) or []) if isinstance(r, dict) and r.get("name")]
    perf = [r for r in doc.get("listedPerf") or [] if isinstance(r, dict) and r.get("name")]
    if not board and not perf:
        return 0
    by_board = {r["name"]: r for r in board}
    by_perf = {r["name"]: r for r in perf}
    matcher = Matcher(board + perf, load_aliases(ALIASES_DIR))
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name") or row.get("bucket") in ("done", "dropped"):
            continue
        hit = matcher.match_strict(row["name"])
        if not hit:
            continue
        b, lp = by_board.get(hit), by_perf.get(hit)        # an alias target may be on neither list yet
        listed = (lp or {}).get("date") or ((b or {}).get("listing") if (b or {}).get("status") == "Listed" else None)
        if listed and str(listed)[:4] != str(today.year):
            continue
        p = patches.setdefault(row["name"], {})
        if listed:
            p.update({"bucket": "done", "stage": "Listed", "stageDate": str(listed)[:10], "listingDate": str(listed)[:10]})
            moved += 1
        elif b and b.get("listing") and not row.get("listingDate"):
            p["listingDate"] = str(b["listing"])[:10]
            moved += 1
    return moved


def _expire(prev: dict, patches: dict, today: dt.date) -> int:
    moved = 0
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        ld = row.get("listingDate")
        if ld and isinstance(ld, str) and ld[:10] < today.isoformat() and row.get("bucket") != "done":
            p = patches.setdefault(row["name"], {})
            p["bucket"] = "done"
            p["stage"] = "Listed"
            p["stageDate"] = ld[:10]
            moved += 1
        # isNew decays after NEW_FOR_DAYS
        if row.get("isNew") and row.get("stageDate") and row["name"] not in patches:
            try:
                age = (today - dt.date.fromisoformat(row["stageDate"][:10])).days
            except ValueError:
                age = 0
            if age > NEW_FOR_DAYS:
                patches[row["name"]] = {"isNew": False}
    return moved


# ---------------------------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------------------------
def run(session: Session, prev: dict, res: Result) -> Result:
    today = _today()
    parents = load_parents()
    wl = watchlist(prev, parents)
    patches: dict[str, dict] = {}
    if not wl:
        res.notes.append("quota: no rows with a ticker in prev; nothing to watch")
    wins: list[str] = []
    last: Exception | None = None
    sebi_rows: list[dict] = []
    found: list[dict] = []
    for name, fn in (("bse_ann", lambda: _from_bse(session, wl, patches, res, today)),
                     ("sebi", lambda: _from_sebi(session, wl, prev, patches, res, today, sebi_rows)),
                     ("nse_ann", lambda: _from_nse_ann(session, today, found, res))):
        try:
            fn()
            res.tried.append({"source": name, "ok": True})
            wins.append(name)
        except SourceError as e:
            res.tried.append({**e.record(), "ok": False})
            last = e
        except Exception as e:  # parser bug == SourceChanged in disguise
            res.tried.append({"kind": "changed", "source": name, "detail": f"{type(e).__name__}: {e}", "ok": False})
            last = e
    ann_ok = "nse_ann" in wins
    if found:
        hits = _leads_to_quota(found, wl, patches, today)
        if hits:
            res.notes.append(f"nse_ann: {hits} quota stage changes from watched parents")
    all_leads = (found if ann_ok else []) + [x for x in prev.get("quotaLeads") or [] if isinstance(x, dict)]
    joined = join_quota_evidence(prev, sebi_rows, all_leads, patches)
    if joined:
        res.notes.append(f"{joined} quota rows carry both the register row and the parent's announcement")
    try:
        companies = nse_symbols.companies(session)
    except SourceError as e:
        companies = None
        res.notes.append(f"discover: NSE equity lists unavailable ({e.detail}); name flags and parent symbols carried forward")
    doc = res.doc or {}
    matched = _reconcile(prev, doc, patches, today)
    if matched:
        res.notes.append(f"{matched} quota rows matched to an issue on the board or listed")
    if _board_rows(doc):                                   # no board in this run: yesterday's quotaFound stays as it is
        seen, fstats = discover(prev, doc, patches, companies, today, all_leads)
        res.replace["quotaFound"] = merge_found(prev.get("quotaFound") or [], seen, doc, today)
        res.notes.append(f"{fstats['reserved']} board issues carry a shareholder reservation, {fstats['unlisted']} not on "
                         f"the quota list; {fstats['disagree']} books show a shareholder category the record does not; "
                         f"{fstats['announced']} parents from the parent's own announcement; "
                         f"{fstats['linked']} quota rows linked by igId; {len(res.replace['quotaFound'])} found held")
    moved = _expire(prev, patches, today)
    if moved:
        res.notes.append(f"{moved} rows past listingDate moved to done")

    # belt and braces: the assembler enforces ownership, but a forbidden field here is our bug
    for name, fields in patches.items():
        bad = set(fields) - ALLOWED_FIELDS
        if bad:
            raise RuntimeError(f"filings tried to write {sorted(bad)} on {name!r}")
    res.rows["quota"] = patches
    if sebi_rows:                      # no SEBI answer -> the names are yesterday's; candidates are still re-read
        expected, stats = build_expected(prev, sebi_rows, today)
        res.notes.append(f"expected: {len(expected)} names; {stats['new']} new from the DRHP register, "
                         f"{stats['rhp']} moved to RHP filed, {stats['launched']} left for the board")
    else:
        expected = [dict(r) for r in prev.get("expected") or [] if isinstance(r, dict)]
    leads = merge_leads(prev.get("quotaLeads") or [], found, today) if ann_ok else \
        [dict(x) for x in prev.get("quotaLeads") or [] if isinstance(x, dict)]
    cstats = attach_candidates(expected, leads, companies)
    res.replace["expected"] = expected
    if ann_ok:
        res.replace["quotaLeads"] = leads
    res.notes.append(f"discover: {cstats['announcement'] + cstats['name']} candidates "
                     f"({cstats['announcement']} by announcement, {cstats['name']} by group name); {len(leads)} leads held")
    kept = sum(1 for r in prev.get("quota") or [] if isinstance(r, dict) and r.get("name") not in patches)
    res.notes.append(f"{len(patches)} rows patched, {kept} kept previous stage")
    if wins:
        res.ok, res.source, res.asOf = True, "+".join(wins), today.isoformat()
        return res
    err = last or RuntimeError("no sources attempted")
    res.ok = False
    res.error = err.record() if isinstance(err, SourceError) else {"kind": "error", "detail": f"{type(err).__name__}: {err}"}
    return res
