"""Adzuna Jobs API — free developer key required.

Docs: https://developer.adzuna.com/docs/search
Env: ADZUNA_APP_ID, ADZUNA_APP_KEY, optional ADZUNA_COUNTRY (default gb)
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from job_sources.linkedin import _dedupe_jobs, _normalize_job

# Map common location phrases → Adzuna country codes
_COUNTRY_HINTS: list[tuple[str, str]] = [
    ("united kingdom", "gb"),
    ("great britain", "gb"),
    ("england", "gb"),
    ("scotland", "gb"),
    ("wales", "gb"),
    ("london", "gb"),
    ("uk", "gb"),
    ("united states", "us"),
    ("usa", "us"),
    ("new york", "us"),
    ("california", "us"),
    ("germany", "de"),
    ("deutschland", "de"),
    ("berlin", "de"),
    ("munich", "de"),
    ("france", "fr"),
    ("paris", "fr"),
    ("netherlands", "nl"),
    ("amsterdam", "nl"),
    ("belgium", "be"),
    ("switzerland", "ch"),
    ("austria", "at"),
    ("ireland", "ie"),
    ("dublin", "ie"),
    ("spain", "es"),
    ("italy", "it"),
    ("canada", "ca"),
    ("australia", "au"),
    ("india", "in"),
    ("poland", "pl"),
    ("sweden", "se"),
    ("norway", "no"),
    ("denmark", "dk"),
    ("finland", "fi"),
    ("brazil", "br"),
    ("south africa", "za"),
    ("singapore", "sg"),
    ("new zealand", "nz"),
]


def _country_from_location(location: str | None) -> str:
    default = (os.getenv("ADZUNA_COUNTRY") or "gb").strip().lower()
    if not location:
        return default
    text = location.lower()
    for hint, code in _COUNTRY_HINTS:
        if re.search(rf"\b{re.escape(hint)}\b", text):
            return code
    return default


def search_adzuna_jobs(
    keywords: str,
    location: str | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    app_id = (os.getenv("ADZUNA_APP_ID") or "").strip()
    app_key = (os.getenv("ADZUNA_APP_KEY") or "").strip()
    if not app_id or not app_key:
        return []

    keywords = (keywords or "").strip()
    if not keywords:
        return []

    limit = max(1, min(int(limit or 15), 50))
    country = _country_from_location(location)
    params: dict[str, str] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": str(limit),
        "what": keywords,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    url = (
        f"https://api.adzuna.com/v1/api/jobs/{urllib.parse.quote(country)}/search/1?"
        + urllib.parse.urlencode(params)
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TalendeurJobMatches/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []

    jobs: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        company = ""
        company_obj = item.get("company")
        if isinstance(company_obj, dict):
            company = company_obj.get("display_name") or ""
        loc = ""
        loc_obj = item.get("location")
        if isinstance(loc_obj, dict):
            loc = loc_obj.get("display_name") or ""
        job = _normalize_job(
            {
                "id": f"adzuna-{item.get('id')}",
                "title": item.get("title") or "",
                "company": company,
                "location": loc or location or "",
                "url": item.get("redirect_url") or item.get("url") or "",
                "description": item.get("description") or "",
            },
            source="adzuna",
        )
        if job:
            # Prefer Adzuna redirect URL as-is (don't force LinkedIn host)
            if item.get("redirect_url"):
                job["url"] = str(item["redirect_url"])
            jobs.append(job)
        if len(jobs) >= limit:
            break

    return _dedupe_jobs(jobs)[:limit]
