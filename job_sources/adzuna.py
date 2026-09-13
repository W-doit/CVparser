"""Adzuna Jobs API — free developer key required.

Docs: https://developer.adzuna.com/docs/search
Env: ADZUNA_APP_ID, ADZUNA_APP_KEY, optional ADZUNA_COUNTRY (default gb)
      — ADZUNA_COUNTRY is only used when no location was provided.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from job_sources.linkedin import _dedupe_jobs, _normalize_job
from job_sources.location import resolve_location


def search_adzuna_jobs(
    keywords: str,
    location: str | None = None,
    limit: int = 15,
    country_code: str | None = None,
) -> list[dict[str, Any]]:
    app_id = (os.getenv("ADZUNA_APP_ID") or "").strip()
    app_key = (os.getenv("ADZUNA_APP_KEY") or "").strip()
    if not app_id or not app_key:
        return []

    keywords = (keywords or "").strip()
    if not keywords:
        return []

    limit = max(1, min(int(limit or 15), 50))
    loc = resolve_location(location)
    resolved_code = (country_code or loc.get("country_code") or "").lower() or None

    # Never invent GB for an explicit but unresolved city (Mumbai bug)
    if location and location.strip() and not loc.get("is_remote") and not resolved_code:
        print(f"Adzuna skipped: unresolved location '{location}' (no country code)")
        return []

    if not resolved_code:
        resolved_code = (os.getenv("ADZUNA_COUNTRY") or "gb").strip().lower()

    params: dict[str, str] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": str(limit),
        "what": keywords,
        "content-type": "application/json",
    }

    # Prefer city for where= when known; else raw location / country name
    if loc.get("is_remote") and loc.get("country_name"):
        params["where"] = loc["country_name"]
    elif loc.get("city"):
        params["where"] = loc["city"]
    elif location and location.strip() and not loc.get("is_remote"):
        params["where"] = location.strip()
    elif loc.get("country_name"):
        params["where"] = loc["country_name"]

    url = (
        f"https://api.adzuna.com/v1/api/jobs/{urllib.parse.quote(resolved_code)}/search/1?"
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
        loc_name = ""
        loc_obj = item.get("location")
        if isinstance(loc_obj, dict):
            loc_name = loc_obj.get("display_name") or ""
        job = _normalize_job(
            {
                "id": f"adzuna-{item.get('id')}",
                "title": item.get("title") or "",
                "company": company,
                "location": loc_name or location or "",
                "url": item.get("redirect_url") or item.get("url") or "",
                "description": item.get("description") or "",
            },
            source="adzuna",
        )
        if job:
            if item.get("redirect_url"):
                job["url"] = str(item["redirect_url"])
            jobs.append(job)
        if len(jobs) >= limit:
            break

    return _dedupe_jobs(jobs)[:limit]
