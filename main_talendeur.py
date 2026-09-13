from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from fastapi.responses import JSONResponse
import uvicorn
import os
import re
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the new LLM-based parser
from llm_parser import GroqCVParser

# Initialize the FastAPI application
app = FastAPI(
    title="Talendeur CV Parser API",
    description="LLM-powered microservice for extracting structured data from CVs using Groq",
    version="2.0.0"
)

# Configure CORS for React app integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize parser (will fail fast if GROQ_API_KEY is missing)
try:
    parser = GroqCVParser()
    _parser_initialized = True
    _init_error = None
except Exception as e:
    parser = None
    _parser_initialized = False
    _init_error = str(e)
    print(f"WARNING: Parser initialization failed: {e}")

@app.post("/parse-cv", tags=["Parser"])
async def extract_cv_data(file: UploadFile = File(...)):
    """
    Endpoint to receive a PDF file, extract text, and use LLM to parse structured data.
    Returns JSON with profile, work experience, education, skills, certifications, and languages.
    """
    
    # Check if parser is initialized
    if not _parser_initialized:
        raise HTTPException(
            status_code=503, 
            detail=f"Parser not initialized. Error: {_init_error}. Please check GROQ_API_KEY environment variable."
        )
    
    # 1. Format Validation: Ensure the uploaded file is a PDF
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are supported.")

    try:
        start_time = time.time()
        
        # 2. Read File Content: Extract raw bytes directly from the upload stream
        pdf_bytes = await file.read()
        
        # 3. Core Processing: Use LLM parser to extract and structure data
        structured_data = parser.parse(pdf_bytes)
        
        # Log processing time
        elapsed = time.time() - start_time
        print(f"CV parsed in {elapsed:.2f}s")
        
        # 4. Success Response: Return the full dictionary as a JSON object
        return JSONResponse(content=structured_data, status_code=200)

    except ValueError as e:
        # Invalid PDF or parsing error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 5. Error Handling: Capture engine failures and return a 500 status code
        raise HTTPException(status_code=500, detail=f"Extraction Engine Error: {str(e)}")

@app.get("/health", tags=["System"])
def health_check():
    """
    Health check endpoint to verify the service is online and Groq API is configured.
    """
    groq_key_set = bool(os.getenv("GROQ_API_KEY"))
    
    return {
        "status": "online" if _parser_initialized else "degraded", 
        "service": "Talendeur Parser (LLM-powered)",
        "parser_initialized": _parser_initialized,
        "groq_api_configured": groq_key_set,
        "error": _init_error if _init_error else None
    }

@app.get("/warmup", tags=["System"])
def warmup():
    """
    Warmup endpoint - not needed for LLM-based parser (kept for compatibility)
    """
    return {
        "status": "success",
        "message": "LLM parser is ready (no warmup needed)",
        "parser_initialized": _parser_initialized
    }


@app.post("/gap-analysis", tags=["Recommendations"])
async def gap_analysis(payload: dict):
    """
    Compare a jobseeker profile snapshot against a target role and return gap recommendations.
    Used by the Profile Recommendations page (#79).
    """
    if not _parser_initialized:
        raise HTTPException(
            status_code=503,
            detail=f"Parser not initialized. Error: {_init_error}."
        )

    target_role = (payload.get("target_role") or "").strip()
    if not target_role:
        raise HTTPException(status_code=400, detail="target_role is required")

    target_organization = payload.get("target_organization")
    profile = payload.get("profile") or {}

    try:
        result = parser.analyze_gap(
            target_role=target_role,
            target_organization=target_organization,
            profile=profile,
        )
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gap analysis failed: {e}")


@app.post("/career-foresight", tags=["Recommendations"])
async def career_foresight(payload: dict):
    """
    Future-ready career guidance: strategic directions and upskilling for an AI-shaped job market.
    Used by the Profile Recommendations page — Stay ahead tab.
    """
    if not _parser_initialized:
        raise HTTPException(
            status_code=503,
            detail=f"Parser not initialized. Error: {_init_error}."
        )

    profile = payload.get("profile") or {}
    industry_preference = (payload.get("industry_preference") or "").strip() or None
    open_to_career_switch = bool(payload.get("open_to_career_switch"))

    try:
        result = parser.analyze_career_foresight(
            profile=profile,
            industry_preference=industry_preference,
            open_to_career_switch=open_to_career_switch,
        )
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Career foresight failed: {e}")


def _heuristic_rank_jobs(profile: dict, jobs: list[dict]) -> dict:
    """Local fallback when Groq ranking fails."""
    corpus_parts = [
        profile.get("headline") or "",
        profile.get("bio") or "",
        " ".join(profile.get("interests") or []),
    ]
    for w in profile.get("work") or []:
        corpus_parts.extend([w.get("title") or "", w.get("company") or "", w.get("description") or ""])
    corpus = " ".join(corpus_parts).lower()

    ranked = []
    for job in jobs:
        title = (job.get("title") or "").lower()
        company = (job.get("company") or "").lower()
        tokens = [t for t in re.split(r"[^a-z0-9+#]+", title) if len(t) > 2]
        hits = sum(1 for t in tokens if t in corpus)
        score = 40 + min(50, hits * 12)
        if any(t in corpus for t in tokens[:2]):
            score += 8
        ranked.append(
            {
                "id": job.get("id"),
                "score": min(95, score),
                "why_fit": f"This opening aligns with keywords from your profile and search for “{job.get('title')}”.",
                "gaps": ["Open the full posting to confirm experience level and required tools."],
            }
        )
    ranked.sort(key=lambda m: m["score"], reverse=True)
    return {
        "summary": f"We found {len(ranked)} opening{'s' if len(ranked) != 1 else ''} that may fit your search.",
        "matches": ranked,
    }


@app.post("/job-matches", tags=["Matches"])
async def job_matches(payload: dict):
    """
    Find job openings that fit a jobseeker profile and return AI-ranked matches.

    Pipeline:
      1) Build search queries (filters + profile)
      2) Fetch from LinkedIn / Adzuna / Arbeitnow (over-fetch)
      3) Hard-filter by location / keywords / role / format
      4) LLM-rank remaining openings (Groq model fallback chain)
    """
    from job_sources.aggregator import search_job_openings
    from job_sources.filters import filter_jobs
    from job_sources.linkedin import derive_search_queries, expand_job_location
    from job_sources.location import resolve_location

    profile = payload.get("profile") or {}
    location_raw = expand_job_location((payload.get("location") or "").strip() or None)
    location_info = resolve_location(location_raw)
    location = location_raw  # pass expanded text to backends
    keywords = (payload.get("keywords") or "").strip() or None
    limit = int(payload.get("limit") or 12)
    limit = max(1, min(limit, 20))

    # Extended search preferences (all optional, free-text)
    preferences = {
        k: (payload.get(k) or "").strip() or None
        for k in (
            "role_title", "opportunity_type", "intent", "time_commitment",
            "compensation", "skill_relationship", "industry", "format",
            "outcome", "level",
        )
    }
    preferences = {k: v for k, v in preferences.items() if v}

    # Keep keywords separate from role_title for hard filters; derive_search_queries combines them
    queries = derive_search_queries(profile, keywords, preferences=preferences)
    collected: list[dict] = []
    backends_used: list[str] = []
    # Over-fetch: filters will drop many false positives (wrong country / employer)
    fetch_per_query = max(12, limit * 2)
    target_raw = max(limit * 4, 30)

    country_code = location_info.get("country_code")
    for query in queries:
        jobs, _backend, tried = search_job_openings(
            query,
            location=location,
            limit=fetch_per_query,
            country_code=country_code,
        )
        for b in tried:
            if b not in backends_used:
                backends_used.append(b)
        collected.extend(jobs)
        if len(collected) >= target_raw:
            break

    # Dedupe by id/url
    seen = set()
    unique_jobs = []
    for job in collected:
        key = job.get("url") or job.get("id")
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append(job)

    pre_filter_count = len(unique_jobs)
    unique_jobs, reject_counts = filter_jobs(
        unique_jobs,
        location_info=location_info if location_info.get("raw") else None,
        keywords=keywords,
        role_title=preferences.get("role_title"),
        format_pref=preferences.get("format"),
        industry=preferences.get("industry"),
    )
    # Cap candidate set for the LLM after hard filters
    unique_jobs = unique_jobs[: max(limit * 2, 18)]
    print(
        f"job-matches: fetched={pre_filter_count} kept={len(unique_jobs)} "
        f"rejected={reject_counts} loc={location_info} queries={queries}"
    )

    if not unique_jobs:
        thin_profile = not (
            (profile.get("headline") or "").strip()
            or any((w.get("title") or "").strip() for w in (profile.get("work") or []) if isinstance(w, dict))
        )
        filter_active = bool(keywords or location or preferences)
        if thin_profile and not keywords and not preferences and not location:
            summary = (
                "No openings found because your profile does not have enough role signals yet "
                "(headline or work experience). Add those on your profile, or enter keywords here."
            )
        elif not backends_used:
            summary = (
                "No openings could be fetched right now (job search backend unavailable). "
                "Please try again shortly, or add a location/keywords to narrow the search."
            )
        elif pre_filter_count > 0 and filter_active:
            bits = []
            if reject_counts.get("location"):
                bits.append("location")
            if reject_counts.get("keywords"):
                bits.append("keywords/company")
            if reject_counts.get("role_title"):
                bits.append("role title")
            focus = " and ".join(bits) if bits else "your filters"
            summary = (
                f"We found openings, but none matched your {focus} filters. "
                "Try a broader city/country, a different company spelling, or clear one filter."
            )
        else:
            summary = (
                "No openings were found for your profile-based search. "
                "Try adding a location or keywords, or refresh in a bit."
            )
        return JSONResponse(
            content={
                "summary": summary,
                "queries": queries,
                "backend": backends_used[0] if backends_used else "none",
                "backends_tried": backends_used,
                "filter_rejected": reject_counts,
                "jobs_fetched": pre_filter_count,
                "matches": [],
            },
            status_code=200,
        )

    # Pass hard constraints into the LLM for residual scoring discipline
    rank_preferences = dict(preferences)
    if keywords:
        rank_preferences["keywords"] = keywords
    if location_info.get("raw"):
        rank_preferences["location"] = location_info["raw"]
    if location_info.get("city"):
        rank_preferences["location_city"] = location_info["city"]
    if location_info.get("country_name"):
        rank_preferences["location_country"] = location_info["country_name"]
    if location_info.get("is_remote"):
        rank_preferences["location_remote"] = "yes"

    ranking = None
    ranking_source = "local"
    if _parser_initialized and parser is not None:
        try:
            ranking = parser.match_jobs(profile, unique_jobs, preferences=rank_preferences)
            ranking_source = "api"
        except Exception as exc:  # noqa: BLE001
            print(f"match_jobs LLM failed, using heuristic: {exc}")
            ranking = _heuristic_rank_jobs(profile, unique_jobs)
    else:
        ranking = _heuristic_rank_jobs(profile, unique_jobs)

    jobs_by_id = {j["id"]: j for j in unique_jobs}
    merged = []
    for item in ranking.get("matches") or []:
        job = jobs_by_id.get(item.get("id"))
        if not job:
            # try fuzzy: match by title if id missing
            continue
        merged.append(
            {
                **job,
                "score": int(item.get("score") or 0),
                "why_fit": item.get("why_fit") or "",
                "gaps": item.get("gaps") or [],
            }
        )

    # If LLM omitted some ids, append remaining with heuristic scores
    present = {m["id"] for m in merged}
    for job in unique_jobs:
        if job["id"] not in present:
            merged.append(
                {
                    **job,
                    "score": 45,
                    "why_fit": "This opening came up in your search. Open the posting to review the full details.",
                    "gaps": [],
                }
            )

    merged.sort(key=lambda m: m.get("score", 0), reverse=True)
    merged = merged[:limit]

    return JSONResponse(
        content={
            "summary": ranking.get("summary") or "",
            "queries": queries,
            "backend": backends_used[0] if backends_used else "none",
            "backends_tried": backends_used,
            "ranking_source": ranking_source,
            "filter_rejected": reject_counts,
            "location_resolved": {
                "city": location_info.get("city"),
                "country_code": location_info.get("country_code"),
                "country_name": location_info.get("country_name"),
                "is_remote": location_info.get("is_remote"),
                "resolved": location_info.get("resolved"),
            },
            "jobs_fetched": len(unique_jobs),
            "matches": merged,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        status_code=200,
    )


# --- Netlify Handler ---
handler = Mangum(app)

if __name__ == "__main__":
    # Start the server using Uvicorn on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

