"""Load yearly Sporting Regulation excerpts and look up a cited article."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG_DIR = ROOT / "data" / "regulations"


def article_key(article: str) -> str:
    return re.sub(r"\s+", "", article or "").lower().rstrip(")")


@lru_cache(maxsize=8)
def load_year(year: int) -> dict:
    path = REG_DIR / f"{year}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_article(year: int, article: str) -> dict | None:
    """Return the stored excerpt for an article, or None if it is not in the file.

    Matching is exact on the normalised article id (for example ``34.14a``).
    A parent id such as ``33.3`` is used only when the citation has no letter
    suffix and that exact id is stored. Nothing is paraphrased here.
    """
    data = load_year(year)
    articles = data.get("articles") or {}
    key = article_key(article)
    if not key:
        return None
    if key in articles:
        return {
            "article": key,
            "text": articles[key],
            "regulation": data.get("title", ""),
            "source_url": data.get("source_url", ""),
            "issue": data.get("issue", ""),
        }
    # Citation "34.14 a)" may be stored as "34.14a" or the body may live on "34.14".
    base = re.sub(r"[a-z]+$", "", key)
    if base and base in articles and base != key:
        return {
            "article": base,
            "text": articles[base],
            "regulation": data.get("title", ""),
            "source_url": data.get("source_url", ""),
            "issue": data.get("issue", ""),
            "matched_as": base,
            "cited_as": key,
        }
    return None


ARTICLE_LINE = re.compile(
    r"(?m)^((?:B\d+(?:\.\d+)+|\d{1,2}\.\d{1,3})(?:\s*[a-z])?)\s+"
)


def split_articles(text: str, limit: int = 900) -> dict[str, str]:
    """Split regulation plain text into article id -> excerpt."""
    cleaned = text.replace("\u00a0", " ")
    matches = list(ARTICLE_LINE.finditer(cleaned))
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        body = re.sub(r"\s+", " ", cleaned[start:end]).strip()
        if len(body) < 40:
            continue
        key = article_key(match.group(1))
        # Contents pages repeat short headings. Keep the longest body.
        if key not in found or len(body) > len(found[key]):
            found[key] = body[:limit]
    return found
