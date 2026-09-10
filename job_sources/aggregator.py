"""Aggregate job search across LinkedIn, Adzuna, and Arbeitnow."""
from __future__ import annotations

from typing import Any

from job_sources.adzuna import search_adzuna_jobs
from job_sources.arbeitnow import search_arbeitnow_jobs
from job_sources.linkedin import _dedupe_jobs, search_linkedin_jobs


def search_job_openings(
    keywords: str,
    location: str | None = None,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """
    Search openings across available backends.

    Order:
      1) LinkedIn MCP / mcporter / Jina (existing stack)
      2) Adzuna (if ADZUNA_APP_ID + ADZUNA_APP_KEY set)
      3) Arbeitnow (free, no key)

    Returns (jobs, primary_backend, backends_used).
    """
    keywords = (keywords or "").strip()
    if not keywords:
        return [], "none", []

    limit = max(1, min(int(limit or 15), 30))
    collected: list[dict[str, Any]] = []
    used: list[str] = []

    # 1) LinkedIn stack
    try:
        jobs, backend = search_linkedin_jobs(keywords, location=location, limit=limit)
        if jobs:
            used.append(backend)
            collected.extend(jobs)
    except Exception as exc:  # noqa: BLE001
        print(f"LinkedIn search error: {exc}")

    # 2) Adzuna — fill gaps / replace when LinkedIn blocked
    if len(collected) < limit:
        try:
            jobs = search_adzuna_jobs(
                keywords, location=location, limit=max(5, limit - len(collected))
            )
            if jobs:
                used.append("adzuna")
                collected.extend(jobs)
        except Exception as exc:  # noqa: BLE001
            print(f"Adzuna search error: {exc}")

    # 3) Arbeitnow — free always-on supplement
    if len(collected) < limit:
        try:
            jobs = search_arbeitnow_jobs(
                keywords, location=location, limit=max(5, limit - len(collected))
            )
            if jobs:
                used.append("arbeitnow")
                collected.extend(jobs)
        except Exception as exc:  # noqa: BLE001
            print(f"Arbeitnow search error: {exc}")

    unique = _dedupe_jobs(collected)[:limit]
    primary = used[0] if used else "none"
    return unique, primary, used
