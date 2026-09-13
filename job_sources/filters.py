"""Hard filters for job openings before LLM ranking."""
from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _norm(text).split() if len(t) > 1]


def _job_corpus(job: dict[str, Any]) -> str:
    parts = [
        job.get("title") or "",
        job.get("company") or "",
        job.get("location") or "",
        job.get("description_snippet") or "",
        job.get("source") or "",
    ]
    return _norm(" ".join(str(p) for p in parts))


def _location_ok(job: dict[str, Any], loc: dict[str, Any]) -> bool:
    """Enforce location constraints. Missing job location fails explicit city/country."""
    job_loc = _norm(job.get("location") or "")
    job_remote = bool(
        job.get("remote")
        or re.search(r"\b(remote|work from home|wfh|worldwide|anywhere)\b", job_loc)
    )

    if not loc or not loc.get("raw"):
        return True

    want_remote = bool(loc.get("is_remote"))
    city = _norm(loc.get("city") or "")
    country = _norm(loc.get("country_name") or "")
    code = (loc.get("country_code") or "").lower()

    # Remote-only request
    if want_remote and not city and not country:
        return job_remote or "remote" in job_loc or "worldwide" in job_loc

    # Remote + geography: must be remote AND (same country OR worldwide)
    if want_remote and (city or country):
        if not (job_remote or "remote" in job_loc):
            return False
        if country and (
            country in job_loc
            or "worldwide" in job_loc
            or "anywhere" in job_loc
            or "global" in job_loc
        ):
            return True
        if city and city in job_loc:
            return True
        # Country-code heuristics in free text
        if code == "in" and re.search(r"\b(india|mumbai|delhi|bengaluru|bangalore|hyderabad)\b", job_loc):
            return True
        if code == "gb" and re.search(r"\b(uk|united kingdom|london|manchester)\b", job_loc):
            return True
        return "worldwide" in job_loc or "anywhere" in job_loc

    # Non-remote: require city or country match in job location
    if not job_loc or job_loc in {"not specified", "n a", "na", "unknown"}:
        return False

    if city and city in job_loc:
        return True
    if country and country in job_loc:
        return True

    # City aliases / country code hints
    if code == "in" and re.search(
        r"\b(india|mumbai|bombay|delhi|bengaluru|bangalore|hyderabad|chennai|pune|kolkata)\b",
        job_loc,
    ):
        return True
    if code == "gb" and re.search(
        r"\b(uk|u k|united kingdom|england|scotland|wales|london|manchester|birmingham)\b",
        job_loc,
    ):
        return True
    if code == "us" and re.search(
        r"\b(usa|u s|united states|new york|san francisco|seattle|chicago|austin)\b",
        job_loc,
    ):
        return True

    # If only remote jobs when user asked for a specific city — reject unless same city/country
    if job_remote and city:
        return city in job_loc
    if job_remote and country:
        return country in job_loc or "worldwide" in job_loc

    return False


_ROLE_WORDS = {
    "engineer",
    "engineering",
    "developer",
    "manager",
    "director",
    "analyst",
    "designer",
    "scientist",
    "consultant",
    "specialist",
    "lead",
    "senior",
    "junior",
    "intern",
    "internship",
    "product",
    "software",
    "data",
    "marketing",
    "sales",
    "ops",
    "operations",
    "hr",
    "recruiter",
    "assistant",
    "associate",
    "officer",
    "head",
    "vp",
    "ceo",
    "cto",
    "cfo",
}


def _keywords_ok(job: dict[str, Any], keywords: str | None) -> bool:
    """Require filter keywords to appear on the job (company/title preferred for brands)."""
    if not keywords or not keywords.strip():
        return True
    corpus = _job_corpus(job)
    company = _norm(job.get("company") or "")
    title = _norm(job.get("title") or "")
    clauses = [c.strip() for c in re.split(r"[,;|]", keywords) if c.strip()]
    if not clauses:
        clauses = [keywords.strip()]
    for clause in clauses:
        tokens = _tokens(clause)
        if not tokens:
            continue
        phrase = _norm(clause)
        # Brand / employer style: short phrase without role words → must hit company or title
        if len(tokens) <= 3 and not any(t in _ROLE_WORDS for t in tokens):
            if phrase in company or all(t in company for t in tokens):
                continue
            if phrase in title or all(t in title for t in tokens):
                continue
            return False
        # Role / skill phrase: all tokens in title+company+snippet
        if phrase in corpus or all(t in corpus for t in tokens):
            continue
        return False
    return True


def _role_ok(job: dict[str, Any], role_title: str | None) -> bool:
    if not role_title or not role_title.strip():
        return True
    title = _norm(job.get("title") or "")
    tokens = [t for t in _tokens(role_title) if t not in {"the", "and", "for", "a", "an"}]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in title)
    # Require majority of meaningful tokens in the job title
    return hits >= max(1, (len(tokens) + 1) // 2)


def _format_ok(job: dict[str, Any], fmt: str | None) -> bool:
    if not fmt or not fmt.strip():
        return True
    f = _norm(fmt)
    corpus = _job_corpus(job)
    job_loc = _norm(job.get("location") or "")
    if "remote" in f:
        return bool(job.get("remote")) or "remote" in corpus or "remote" in job_loc
    if "hybrid" in f:
        return "hybrid" in corpus or "hybrid" in job_loc
    if "on site" in f or "onsite" in f or "office" in f:
        return not (
            bool(job.get("remote"))
            or re.search(r"\bremote only\b", corpus)
        )
    return True


def filter_jobs(
    jobs: list[dict[str, Any]],
    *,
    location_info: dict[str, Any] | None = None,
    keywords: str | None = None,
    role_title: str | None = None,
    format_pref: str | None = None,
    industry: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Apply hard filters. Returns (kept, rejection_counts).
    """
    rejected = {
        "location": 0,
        "keywords": 0,
        "role_title": 0,
        "format": 0,
        "industry": 0,
    }
    kept: list[dict[str, Any]] = []

    for job in jobs:
        if location_info and location_info.get("raw") and not _location_ok(job, location_info):
            rejected["location"] += 1
            continue
        if not _keywords_ok(job, keywords):
            rejected["keywords"] += 1
            continue
        if not _role_ok(job, role_title):
            rejected["role_title"] += 1
            continue
        if not _format_ok(job, format_pref):
            rejected["format"] += 1
            continue
        if industry and industry.strip():
            corp = _job_corpus(job)
            ind_tokens = _tokens(industry)
            if ind_tokens and not any(t in corp for t in ind_tokens):
                # Soft for industry: don't hard-drop if metadata thin — only drop if
                # title/company clearly contradict? Keep soft: require at least one token
                # when description exists; else keep.
                desc = (job.get("description_snippet") or "").strip()
                if desc and len(ind_tokens) <= 3:
                    rejected["industry"] += 1
                    continue
        kept.append(job)

    return kept, rejected
