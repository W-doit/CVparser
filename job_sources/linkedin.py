"""
LinkedIn job search backends (Agent-Reach style).

Primary: linkedin-scraper-mcp / mcp-server-linkedin via HTTP MCP or mcporter CLI
Fallback: Jina Reader on public LinkedIn jobs search URLs
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from typing import Any


def _normalize_job(raw: dict[str, Any], source: str = "linkedin") -> dict[str, Any] | None:
    title = (raw.get("title") or raw.get("job_title") or raw.get("name") or "").strip()
    if not title:
        return None

    company = (
        raw.get("company")
        or raw.get("companyName")
        or raw.get("company_name")
        or raw.get("organization")
        or ""
    )
    location = raw.get("location") or raw.get("job_location") or raw.get("place") or ""
    url = (
        raw.get("url")
        or raw.get("link")
        or raw.get("job_url")
        or raw.get("applyUrl")
        or raw.get("linkedin_url")
        or ""
    )
    description = (
        raw.get("description_snippet")
        or raw.get("description")
        or raw.get("snippet")
        or raw.get("summary")
        or ""
    )
    if isinstance(description, str) and len(description) > 600:
        description = description[:597] + "..."

    job_id = str(raw.get("id") or raw.get("job_id") or "")
    if not job_id:
        basis = f"{title}|{company}|{url}".lower()
        job_id = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    if url and not url.startswith("http"):
        url = f"https://www.linkedin.com{url}" if url.startswith("/") else url

    return {
        "id": job_id,
        "title": title,
        "company": str(company).strip() or "Unknown company",
        "location": str(location).strip() or "Not specified",
        "url": url or f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(title)}",
        "description_snippet": str(description).strip(),
        "source": source,
    }


def _dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for job in jobs:
        key = (job.get("url") or job.get("id") or "").lower()
        title_company = f"{job.get('title', '')}|{job.get('company', '')}".lower()
        fingerprint = key or title_company
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(job)
    return out


def _mcp_http_search(keywords: str, location: str | None, limit: int) -> list[dict[str, Any]]:
    """Call LinkedIn MCP over streamable HTTP if LINKEDIN_MCP_URL is set."""
    base = (os.getenv("LINKEDIN_MCP_URL") or "").rstrip("/")
    if not base:
        return []

    # Prefer a simple JSON bridge if the host exposes one (optional custom wrapper)
    bridge = os.getenv("LINKEDIN_MCP_BRIDGE_URL", "").rstrip("/")
    if bridge:
        payload = json.dumps(
            {"keywords": keywords, "location": location or "", "limit": limit}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{bridge}/search_jobs",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = data if isinstance(data, list) else data.get("jobs") or data.get("result") or []
        return [j for j in (_normalize_job(r, "linkedin-mcp") for r in rows) if j]

    # Generic MCP tools/call style (best-effort; depends on server transport)
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_jobs",
                "arguments": {
                    "keywords": keywords,
                    "location": location or "",
                    "limit": limit,
                    "max_pages": 1,
                },
            },
        }
    ).encode("utf-8")

    endpoints = [
        f"{base}/mcp",
        f"{base}/",
        base,
    ]
    last_err: Exception | None = None
    for url in endpoints:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8")
            # Handle plain JSON or simple SSE data: lines
            text = body
            if "data:" in body:
                chunks = [
                    line[5:].strip()
                    for line in body.splitlines()
                    if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]")
                ]
                text = chunks[-1] if chunks else body
            parsed = json.loads(text)
            result = parsed.get("result", parsed)
            content = result.get("content") if isinstance(result, dict) else None
            if isinstance(content, list):
                # MCP content blocks often wrap text JSON
                assembled = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        assembled.append(block.get("text") or "")
                joined = "\n".join(assembled).strip()
                if joined:
                    try:
                        result = json.loads(joined)
                    except json.JSONDecodeError:
                        result = {"raw": joined}
            rows: list[Any]
            if isinstance(result, list):
                rows = result
            elif isinstance(result, dict):
                rows = result.get("jobs") or result.get("results") or result.get("data") or []
                if not rows and result.get("raw"):
                    rows = _parse_jobs_from_markdown(str(result["raw"]), limit)
            else:
                rows = []
            normalized = [j for j in (_normalize_job(r, "linkedin-mcp") for r in rows if isinstance(r, dict)) if j]
            if normalized:
                return normalized[:limit]
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        print(f"LinkedIn MCP HTTP search failed: {last_err}")
    return []


def _mcporter_search(keywords: str, location: str | None, limit: int) -> list[dict[str, Any]]:
    """Try mcporter CLI (Agent-Reach style) if available on PATH."""
    if os.getenv("LINKEDIN_DISABLE_MCPORTER", "").lower() in ("1", "true", "yes"):
        return []

    # Try a few known tool names used by Agent-Reach / linkedin MCP packages
    candidates = [
        f'linkedin-scraper.search_jobs(keyword: "{keywords}", limit: {limit})',
        f'linkedin.search_jobs(keywords: "{keywords}", location: "{location or ""}", max_pages: 1)',
        f'linkedin.search_jobs keywords="{keywords}" location="{location or "Remote"}" max_pages=1',
    ]

    for call in candidates:
        try:
            completed = subprocess.run(
                ["mcporter", "call", call],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                continue
            out = (completed.stdout or "").strip()
            if not out:
                continue
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                # Sometimes mcporter prints YAML/text — fall through to markdown parser
                jobs = _parse_jobs_from_markdown(out, limit)
                if jobs:
                    return jobs
                continue
            rows = data if isinstance(data, list) else data.get("jobs") or data.get("results") or []
            normalized = [
                j for j in (_normalize_job(r, "linkedin-mcp") for r in rows if isinstance(r, dict)) if j
            ]
            if normalized:
                return normalized[:limit]
        except FileNotFoundError:
            return []
        except Exception as exc:  # noqa: BLE001
            print(f"mcporter LinkedIn search failed: {exc}")
            continue
    return []


def _parse_jobs_from_markdown(text: str, limit: int) -> list[dict[str, Any]]:
    """Extract job-like entries from Jina/markdown LinkedIn search pages."""
    jobs: list[dict[str, Any]] = []

    # Pattern: markdown links to LinkedIn job views
    link_re = re.compile(
        r"\[([^\]]+)\]\((https?://(?:www\.)?linkedin\.com/jobs/view/[^)\s]+)\)",
        re.IGNORECASE,
    )
    for match in link_re.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).split("?")[0]
        # Skip generic chrome links
        if title.lower() in ("linkedin", "sign in", "join now", "jobs"):
            continue
        # Try to find company on nearby lines
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        window = text[start:end]
        company_match = re.search(
            r"(?:Company|at|·)\s*[:\-]?\s*([A-Z][^\n|]{1,80})",
            window,
        )
        company = company_match.group(1).strip() if company_match else ""
        location_match = re.search(
            r"(Remote|Hybrid|[A-Z][a-zA-Z\s\-]+(?:,\s*[A-Z]{2})?)",
            window,
        )
        location = location_match.group(1).strip() if location_match else ""
        job = _normalize_job(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description_snippet": "",
            },
            source="linkedin-jina",
        )
        if job:
            jobs.append(job)
        if len(jobs) >= limit:
            break

    if jobs:
        return _dedupe_jobs(jobs)[:limit]

    # Fallback: numbered or bulleted title lines near "jobs"
    line_re = re.compile(
        r"^(?:[\-\*]|\d+[\.)])\s*(.+?)(?:\s+[—\-|·]\s+(.+))?$",
        re.MULTILINE,
    )
    for match in line_re.finditer(text):
        title = match.group(1).strip()
        company = (match.group(2) or "").strip()
        if len(title) < 4 or len(title) > 120:
            continue
        if "linkedin" in title.lower():
            continue
        job = _normalize_job(
            {
                "title": title,
                "company": company,
                "location": "",
                "url": f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(title)}",
                "description_snippet": "",
            },
            source="linkedin-jina",
        )
        if job:
            jobs.append(job)
        if len(jobs) >= limit:
            break

    return _dedupe_jobs(jobs)[:limit]


def _jina_search(keywords: str, location: str | None, limit: int) -> list[dict[str, Any]]:
    prefix = (os.getenv("JINA_READER_PREFIX") or "https://r.jina.ai/").rstrip("/") + "/"
    params = {"keywords": keywords}
    if location:
        params["location"] = location
    linkedin_url = "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)
    reader_url = prefix + linkedin_url

    req = urllib.request.Request(
        reader_url,
        headers={"User-Agent": "TalendeurJobMatches/1.0", "Accept": "text/plain"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    return _parse_jobs_from_markdown(text, limit)


def search_linkedin_jobs(
    keywords: str,
    location: str | None = None,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], str]:
    """
    Search LinkedIn jobs.

    Returns (jobs, backend_used) where backend_used is one of:
    linkedin-mcp, linkedin-mcporter, linkedin-jina, none
    """
    keywords = (keywords or "").strip()
    if not keywords:
        return [], "none"

    limit = max(1, min(int(limit or 15), 30))

    # 1) HTTP MCP / bridge
    try:
        jobs = _mcp_http_search(keywords, location, limit)
        if jobs:
            return _dedupe_jobs(jobs)[:limit], "linkedin-mcp"
    except Exception as exc:  # noqa: BLE001
        print(f"LinkedIn MCP path error: {exc}")

    # 2) mcporter CLI
    try:
        jobs = _mcporter_search(keywords, location, limit)
        if jobs:
            return _dedupe_jobs(jobs)[:limit], "linkedin-mcporter"
    except Exception as exc:  # noqa: BLE001
        print(f"LinkedIn mcporter path error: {exc}")

    # 3) Jina Reader fallback
    try:
        jobs = _jina_search(keywords, location, limit)
        if jobs:
            return _dedupe_jobs(jobs)[:limit], "linkedin-jina"
    except Exception as exc:  # noqa: BLE001
        print(f"LinkedIn Jina path error: {exc}")

    return [], "none"


def derive_search_queries(profile: dict[str, Any], explicit_keywords: str | None = None) -> list[str]:
    """Build 1–3 LinkedIn search queries from profile or explicit keywords."""
    if explicit_keywords and explicit_keywords.strip():
        return [explicit_keywords.strip()]

    queries: list[str] = []
    headline = (profile.get("headline") or "").strip()
    if headline:
        queries.append(re.sub(r"[|•·].*$", "", headline).strip()[:80])

    work = profile.get("work") or []
    for w in work[:2]:
        title = (w.get("title") or "").strip()
        if title and title.lower() not in {q.lower() for q in queries}:
            queries.append(title[:80])

    interests = profile.get("interests") or []
    if isinstance(interests, list) and interests and len(queries) < 2:
        queries.append(str(interests[0])[:80])

    if not queries:
        queries.append("professional")

    return queries[:3]
