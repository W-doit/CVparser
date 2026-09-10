"""Arbeitnow public job-board API — free, no key.

Docs: https://www.arbeitnow.com/api/job-board-api
Returns a paginated board feed; we filter client-side by keywords/location.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any

from job_sources.linkedin import _dedupe_jobs, _normalize_job

_API_URL = "https://www.arbeitnow.com/api/job-board-api"
_CACHE: dict[str, Any] = {"fetched_at": 0.0, "jobs": []}
_CACHE_TTL_S = 30 * 60  # 30 minutes


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _fetch_board() -> list[dict[str, Any]]:
    now = time.time()
    if _CACHE["jobs"] and now - float(_CACHE["fetched_at"]) < _CACHE_TTL_S:
        return list(_CACHE["jobs"])

    req = urllib.request.Request(
        _API_URL,
        headers={"User-Agent": "TalendeurJobMatches/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))

    data = payload.get("data") if isinstance(payload, dict) else None
    jobs = data if isinstance(data, list) else []
    _CACHE["fetched_at"] = now
    _CACHE["jobs"] = jobs
    return list(jobs)


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9+#]+", (text or "").lower()) if len(t) > 2]


def search_arbeitnow_jobs(
    keywords: str,
    location: str | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    keywords = (keywords or "").strip()
    if not keywords:
        return []

    limit = max(1, min(int(limit or 15), 50))
    try:
        board = _fetch_board()
    except Exception as exc:  # noqa: BLE001
        print(f"Arbeitnow fetch error: {exc}")
        return []

    kw_tokens = _tokens(keywords)
    loc_tokens = _tokens(location or "")
    want_remote = bool(location and re.search(r"\bremote\b", location, re.I))

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in board:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        company = str(item.get("company_name") or "")
        loc = str(item.get("location") or "")
        tags = " ".join(str(t) for t in (item.get("tags") or []))
        types = " ".join(str(t) for t in (item.get("job_types") or []))
        desc = _strip_html(str(item.get("description") or ""))[:800]
        corpus = f"{title} {company} {loc} {tags} {types} {desc}".lower()

        hits = sum(1 for t in kw_tokens if t in corpus)
        if kw_tokens and hits == 0:
            continue

        if loc_tokens and not want_remote:
            if not any(t in loc.lower() or t in corpus for t in loc_tokens):
                # Soft filter: keep remotes even if city mismatch
                if not item.get("remote"):
                    continue

        if want_remote and not item.get("remote") and "remote" not in corpus:
            continue

        score = hits * 10
        if item.get("remote"):
            score += 2
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    jobs: list[dict[str, Any]] = []
    for _score, item in scored[:limit]:
        job = _normalize_job(
            {
                "id": f"arbeitnow-{item.get('slug') or item.get('url')}",
                "title": item.get("title") or "",
                "company": item.get("company_name") or "",
                "location": (
                    "Remote"
                    if item.get("remote") and not item.get("location")
                    else item.get("location") or ("Remote" if item.get("remote") else "")
                ),
                "url": item.get("url") or "",
                "description": _strip_html(str(item.get("description") or ""))[:600],
            },
            source="arbeitnow",
        )
        if job:
            if item.get("url"):
                job["url"] = str(item["url"])
            jobs.append(job)

    return _dedupe_jobs(jobs)[:limit]
