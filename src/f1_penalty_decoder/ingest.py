"""Download public FIA decision listings and build data/decisions.json.

Usage:
    python -m f1_penalty_decoder.ingest
    python -m f1_penalty_decoder.ingest --seasons 2024 2025

The script is single-threaded. It pauses between requests and backs off on
HTTP 429 or 403. A PDF already cached under a hash of its full URL is not
downloaded again. A failure is recorded. The script does not invent a decision
to fill a gap. PDFs under data/.cache are not part of the published dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from f1_penalty_decoder.parse_decision import parse_decision_text, record_is_consistent
from f1_penalty_decoder.regulations import split_articles

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = DATA / ".cache"
USER_AGENT = "f1-penalty-decoder/0.1 (unofficial fan research; public documents only)"

SEASONS = {
    2022: "https://www.fia.com/documents/season/season-2022-2005/championships/fia-formula-one-world-championship-14",
    2023: "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2023-2042",
    2024: "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2024-2043",
    2025: "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071",
    2026: "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072",
}

# Latest issue published on the FIA regulations index for that calendar year.
# A race weekend can still have been run under an earlier issue. The citation
# always names this file rather than implying it was the issue on the day.
REGULATIONS = {
    2022: "https://www.fia.com/sites/default/files/fia_2022_formula_1_sporting_regulations_-_issue_9_-_2022-10-19_0.pdf",
    2023: "https://www.fia.com/sites/default/files/fia_2023_formula_1_sporting_regulations_-_issue_8_-_2023-12-06_0.pdf",
    2024: "https://www.fia.com/sites/default/files/fia_2024_formula_1_sporting_regulations_-_issue_7_-_2024-07-31.pdf",
    2025: "https://www.fia.com/system/files/documents/fia_2025_formula_1_sporting_regulations_-_issue_5_-_2025-04-30.pdf",
    2026: "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_09_-_2026-10-01.pdf",
}

INCLUDE = ("infringement", "offence", "offense", "decision")
EXCLUDE = (
    "summons",
    "classification",
    "scrutineering",
    "procedure",
    "notes",
    "starting grid",
    "championship points",
    "timetable",
    "entry list",
    "curfew",
    "pirelli",
    "visa",
    "tyre",
    "tire",
    "power unit element",
    "new pu",
    "parc ferme issues",
    "right of review",
)


# Pause between requests. 429 and 403 back off further, then the document is
# recorded as a failure so a later run can resume from the cache.
REQUEST_GAP_SECONDS = 1.5


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    delay = 20.0
    last_error: Exception | None = None
    for attempt in range(4):
        if attempt:
            time.sleep(delay)
            delay *= 2
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            time.sleep(REQUEST_GAP_SECONDS)
            return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (429, 403) and attempt < 3:
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"no response for {url}")


def cache_filename(url: str) -> str:
    """Cache name is a hash of the full URL, so shared path prefixes cannot collide."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest() + ".pdf"


def absolute(url: str) -> str:
    if url.startswith("http"):
        path = urllib.parse.urlsplit(url).path
        return "https://www.fia.com" + urllib.parse.quote(urllib.parse.unquote(path), safe="/")
    path = urllib.parse.unquote(url if url.startswith("/") else "/" + url)
    return "https://www.fia.com" + urllib.parse.quote(path, safe="/")


def event_links(season_html: str, season_url: str) -> list[tuple[str, str]]:
    pairs = re.findall(r'value="([^"]*/event/[^"]+)"[^>]*>([^<]+)', season_html)
    found = []
    for href, name in pairs:
        name = name.strip()
        if "Grand Prix" not in name:
            continue
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = "https://www.fia.com" + href
        else:
            url = season_url.rstrip("/") + "/" + href
        found.append((urllib.parse.unquote(name), url.replace("&amp;", "&")))
    # Unique, stable order.
    seen = set()
    unique = []
    for item in found:
        if item[1] in seen:
            continue
        seen.add(item[1])
        unique.append(item)
    return unique


def listed_documents(event_html: str) -> list[dict]:
    rows = re.findall(
        r'href="([^"]+\.pdf)"[\s\S]{0,1200}?title-field[\s\S]{0,400}?field-item even">([^<]+)',
        event_html,
        flags=re.IGNORECASE,
    )
    docs = []
    for href, title in rows:
        title = re.sub(r"\s+", " ", title).strip()
        docs.append({"title": title, "url": absolute(href)})
    return docs


def wanted(title: str) -> bool:
    low = title.lower()
    if any(word in low for word in EXCLUDE):
        return False
    return any(word in low for word in INCLUDE)


def pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages[:4]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80]


def one_pdf(item: dict) -> dict:
    url = item["url"]
    path = CACHE / "pdf" / cache_filename(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.stat().st_size > 1000:
            data = path.read_bytes()
        else:
            data = fetch_bytes(url)
            path.write_bytes(data)
        text = pdf_text(data)
    except Exception as exc:  # noqa: BLE001 - recorded, not invented
        return {
            **item,
            "status": "fetch_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if not text.strip():
        return {**item, "status": "empty_text", "error": "PDF extracted no text"}
    parsed = parse_decision_text(text, item["title"])
    if not parsed["penalty"] and not parsed["article"] and not parsed["incident_summary"]:
        return {**item, "status": "unparsed", "error": "No fact, article, or decision line found"}
    record_id = f"{item['season']}-{slug(item['event'])}-{slug(item['title'])}"
    return {
        "id": record_id[:140],
        "status": "ok",
        "season": item["season"],
        "event": item["event"],
        "session": parsed["session"],
        "session_type": parsed.get("session_type") or "",
        "driver": parsed["driver"],
        "car_number": parsed["car_number"],
        "competitor": parsed["competitor"],
        "incident_summary": parsed["incident_summary"],
        "incident_type": parsed["incident_type"],
        "article": parsed["article"],
        "offence_text": parsed["offence_text"],
        "penalty": parsed["penalty"],
        "penalty_kind": parsed["penalty_kind"],
        "reason": parsed["reason"],
        "document_url": url,
        "document_title": item["title"],
        "published": item.get("published") or "",
    }


def ingest_regulations() -> list[dict]:
    notes = []
    out_dir = DATA / "regulations"
    out_dir.mkdir(parents=True, exist_ok=True)
    for year, url in REGULATIONS.items():
        dest = CACHE / "regulations" / f"{year}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not dest.exists() or dest.stat().st_size < 1000:
                dest.write_bytes(fetch_bytes(url, timeout=120))
            text = pdf_text_all(dest.read_bytes())
            articles = split_articles(text)
            issue = ""
            match = re.search(r"Issue\s+([0-9]+)", text[:500], flags=re.IGNORECASE)
            if match:
                issue = f"Issue {match.group(1)}"
            payload = {
                "year": year,
                "title": f"{year} FIA Formula One Sporting Regulations",
                "issue": issue,
                "source_url": url,
                "article_count": len(articles),
                "articles": articles,
            }
            (out_dir / f"{year}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            notes.append({"year": year, "status": "ok", "articles": len(articles), "url": url})
        except Exception as exc:  # noqa: BLE001
            notes.append({"year": year, "status": "fetch_failed", "error": str(exc), "url": url})
    return notes


def pdf_text_all(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def collect_listings(seasons: list[int]) -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    failures: list[dict] = []
    for year in seasons:
        page = SEASONS[year]
        try:
            html = fetch_bytes(page).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            failures.append({"season": year, "url": page, "error": str(exc), "stage": "season"})
            continue
        events = event_links(html, page)
        if not events:
            failures.append({"season": year, "url": page, "error": "no Grand Prix links", "stage": "season"})
        for name, url in events:
            try:
                event_html = fetch_bytes(url).decode("utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                failures.append({"season": year, "event": name, "url": url, "error": str(exc), "stage": "event"})
                continue
            for doc in listed_documents(event_html):
                if not wanted(doc["title"]):
                    continue
                items.append({"season": year, "event": name, **doc})
    return items, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FIA F1 stewards' decisions")
    parser.add_argument("--seasons", nargs="*", type=int, default=sorted(SEASONS))
    parser.add_argument("--limit", type=int, default=0, help="Download at most N PDFs that are not cached (0 = all)")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    print("regulations", flush=True)
    reg_notes = ingest_regulations()
    print(json.dumps(reg_notes), flush=True)
    print("listings", flush=True)
    items, failures = collect_listings(args.seasons)
    if args.limit:
        items = items[: args.limit]
    print(f"documents {len(items)} listing_failures {len(failures)}", flush=True)
    decisions = []
    for index, item in enumerate(items, start=1):
        result = one_pdf(item)
        if result.get("status") == "ok":
            ok, reason = record_is_consistent(result)
            if ok:
                decisions.append(result)
            else:
                failures.append({**result, "status": "dropped", "error": reason})
        else:
            failures.append(result)
        if index % 25 == 0:
            print(f"processed {index}/{len(items)} kept {len(decisions)}", flush=True)
    decisions.sort(key=lambda row: (row["season"], row["event"], row["document_title"]))
    counts: dict[str, int] = {}
    for row in decisions:
        counts[str(row["season"])] = counts.get(str(row["season"]), 0) + 1
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "FIA decision documents at fia.com. Unofficial collection.",
        "seasons": args.seasons,
        "counts_by_season": counts,
        "decision_count": len(decisions),
        "failure_count": len(failures),
        "decisions": decisions,
    }
    (DATA / "decisions.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "ingest_failures.json").write_text(
        json.dumps({"count": len(failures), "items": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA / "regulation_fetch.json").write_text(json.dumps(reg_notes, indent=2), encoding="utf-8")
    print(json.dumps({"counts": counts, "failures": len(failures)}, indent=2))


if __name__ == "__main__":
    main()
