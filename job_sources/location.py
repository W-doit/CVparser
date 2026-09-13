"""Location normalisation for job search backends."""
from __future__ import annotations

import re
from typing import Any

# Country aliases / names → ISO-2 (Adzuna path codes)
_COUNTRY_ALIASES: dict[str, str] = {
    "united kingdom": "gb",
    "great britain": "gb",
    "britain": "gb",
    "england": "gb",
    "scotland": "gb",
    "wales": "gb",
    "northern ireland": "gb",
    "uk": "gb",
    "u.k": "gb",
    "u.k.": "gb",
    "gb": "gb",
    "gbr": "gb",
    "united states": "us",
    "united states of america": "us",
    "usa": "us",
    "u.s": "us",
    "u.s.a": "us",
    "us": "us",
    "america": "us",
    "germany": "de",
    "deutschland": "de",
    "de": "de",
    "france": "fr",
    "fr": "fr",
    "netherlands": "nl",
    "holland": "nl",
    "the netherlands": "nl",
    "nl": "nl",
    "belgium": "be",
    "be": "be",
    "switzerland": "ch",
    "ch": "ch",
    "austria": "at",
    "at": "at",
    "ireland": "ie",
    "eire": "ie",
    "ie": "ie",
    "spain": "es",
    "españa": "es",
    "espana": "es",
    "es": "es",
    "italy": "it",
    "italia": "it",
    "it": "it",
    "canada": "ca",
    "ca": "ca",
    "australia": "au",
    "au": "au",
    "india": "in",
    "in": "in",
    "bharat": "in",
    "poland": "pl",
    "pl": "pl",
    "sweden": "se",
    "se": "se",
    "norway": "no",
    "no": "no",
    "denmark": "dk",
    "dk": "dk",
    "finland": "fi",
    "fi": "fi",
    "brazil": "br",
    "brasil": "br",
    "br": "br",
    "south africa": "za",
    "za": "za",
    "singapore": "sg",
    "sg": "sg",
    "new zealand": "nz",
    "nz": "nz",
    "united arab emirates": "ae",
    "uae": "ae",
    "u.a.e": "ae",
    "ae": "ae",
    "portugal": "pt",
    "pt": "pt",
    "japan": "jp",
    "jp": "jp",
    "china": "cn",
    "cn": "cn",
    "south korea": "kr",
    "korea": "kr",
    "kr": "kr",
    "mexico": "mx",
    "mx": "mx",
    "argentina": "ar",
    "ar": "ar",
    "chile": "cl",
    "cl": "cl",
    "czech republic": "cz",
    "czechia": "cz",
    "cz": "cz",
    "hungary": "hu",
    "hu": "hu",
    "romania": "ro",
    "ro": "ro",
    "greece": "gr",
    "gr": "gr",
    "turkey": "tr",
    "türkiye": "tr",
    "tr": "tr",
    "israel": "il",
    "il": "il",
    "philippines": "ph",
    "ph": "ph",
    "indonesia": "id",
    "id": "id",
    "malaysia": "my",
    "my": "my",
    "thailand": "th",
    "th": "th",
    "vietnam": "vn",
    "vn": "vn",
    "nigeria": "ng",
    "ng": "ng",
    "kenya": "ke",
    "ke": "ke",
    "egypt": "eg",
    "eg": "eg",
    "pakistan": "pk",
    "pk": "pk",
    "bangladesh": "bd",
    "bd": "bd",
    "sri lanka": "lk",
    "lk": "lk",
}

# City / metro → ISO-2
_CITY_TO_COUNTRY: dict[str, str] = {
    # India
    "mumbai": "in",
    "bombay": "in",
    "delhi": "in",
    "new delhi": "in",
    "bengaluru": "in",
    "bangalore": "in",
    "hyderabad": "in",
    "chennai": "in",
    "madras": "in",
    "kolkata": "in",
    "calcutta": "in",
    "pune": "in",
    "gurgaon": "in",
    "gurugram": "in",
    "noida": "in",
    "ahmedabad": "in",
    "jaipur": "in",
    "kochi": "in",
    "cochin": "in",
    # UK
    "london": "gb",
    "manchester": "gb",
    "birmingham": "gb",
    "leeds": "gb",
    "glasgow": "gb",
    "edinburgh": "gb",
    "bristol": "gb",
    "liverpool": "gb",
    "cambridge": "gb",
    "oxford": "gb",
    "reading": "gb",
    "cardiff": "gb",
    "belfast": "gb",
    # US
    "new york": "us",
    "nyc": "us",
    "san francisco": "us",
    "sf": "us",
    "los angeles": "us",
    "la": "us",
    "seattle": "us",
    "chicago": "us",
    "boston": "us",
    "austin": "us",
    "denver": "us",
    "miami": "us",
    "washington": "us",
    "washington dc": "us",
    "atlanta": "us",
    # EU / other
    "berlin": "de",
    "munich": "de",
    "münchen": "de",
    "hamburg": "de",
    "frankfurt": "de",
    "cologne": "de",
    "köln": "de",
    "paris": "fr",
    "lyon": "fr",
    "amsterdam": "nl",
    "rotterdam": "nl",
    "brussels": "be",
    "zurich": "ch",
    "geneva": "ch",
    "vienna": "at",
    "dublin": "ie",
    "madrid": "es",
    "barcelona": "es",
    "rome": "it",
    "milan": "it",
    "milano": "it",
    "lisbon": "pt",
    "porto": "pt",
    "stockholm": "se",
    "oslo": "no",
    "copenhagen": "dk",
    "helsinki": "fi",
    "warsaw": "pl",
    "krakow": "pl",
    "prague": "cz",
    "budapest": "hu",
    "toronto": "ca",
    "vancouver": "ca",
    "montreal": "ca",
    "sydney": "au",
    "melbourne": "au",
    "brisbane": "au",
    "auckland": "nz",
    "dubai": "ae",
    "abu dhabi": "ae",
    "singapore": "sg",
    "tokyo": "jp",
    "osaka": "jp",
    "hong kong": "cn",
    "shanghai": "cn",
    "beijing": "cn",
    "sao paulo": "br",
    "são paulo": "br",
    "rio de janeiro": "br",
    "mexico city": "mx",
    "johannesburg": "za",
    "cape town": "za",
    "lagos": "ng",
    "nairobi": "ke",
    "cairo": "eg",
    "tel aviv": "il",
    "istanbul": "tr",
    "bangkok": "th",
    "jakarta": "id",
    "manila": "ph",
    "kuala lumpur": "my",
}

_COUNTRY_NAMES: dict[str, str] = {
    "gb": "United Kingdom",
    "us": "United States",
    "de": "Germany",
    "fr": "France",
    "nl": "Netherlands",
    "be": "Belgium",
    "ch": "Switzerland",
    "at": "Austria",
    "ie": "Ireland",
    "es": "Spain",
    "it": "Italy",
    "ca": "Canada",
    "au": "Australia",
    "in": "India",
    "pl": "Poland",
    "se": "Sweden",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "br": "Brazil",
    "za": "South Africa",
    "sg": "Singapore",
    "nz": "New Zealand",
    "ae": "United Arab Emirates",
    "pt": "Portugal",
    "jp": "Japan",
    "cn": "China",
    "kr": "South Korea",
    "mx": "Mexico",
    "ar": "Argentina",
    "cl": "Chile",
    "cz": "Czech Republic",
    "hu": "Hungary",
    "ro": "Romania",
    "gr": "Greece",
    "tr": "Turkey",
    "il": "Israel",
    "ph": "Philippines",
    "id": "Indonesia",
    "my": "Malaysia",
    "th": "Thailand",
    "vn": "Vietnam",
    "ng": "Nigeria",
    "ke": "Kenya",
    "eg": "Egypt",
    "pk": "Pakistan",
    "bd": "Bangladesh",
    "lk": "Sri Lanka",
}


def _norm(value: str) -> str:
    text = (value or "").lower().replace(".", " ")
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_remote_location(location: str | None) -> bool:
    if not location:
        return False
    return bool(re.search(r"\b(remote|work from home|wfh|worldwide|anywhere)\b", location, re.I))


def resolve_location(location: str | None) -> dict[str, Any]:
    """
    Resolve free-text location into structured fields.

    Returns:
      raw, city, country_code, country_name, is_remote, resolved
    Never invents a country when the text is unknown — callers must not
    fall back to GB for an explicit unknown city (that caused Mumbai→UK).
    """
    raw = (location or "").strip()
    if not raw:
        return {
            "raw": "",
            "city": None,
            "country_code": None,
            "country_name": None,
            "is_remote": False,
            "resolved": False,
        }

    remote = is_remote_location(raw)
    # Strip remote tokens for geo parsing when combined ("Remote, India")
    geo = re.sub(
        r"\b(remote|work from home|wfh|worldwide|anywhere)\b",
        " ",
        raw,
        flags=re.I,
    )
    geo = re.sub(r"[\s,;/|]+", " ", geo).strip()
    key = _norm(geo)

    city = None
    country_code = None

    if key:
        # Exact country
        if key in _COUNTRY_ALIASES:
            country_code = _COUNTRY_ALIASES[key]
        # Exact city
        elif key in _CITY_TO_COUNTRY:
            city = geo
            country_code = _CITY_TO_COUNTRY[key]
        else:
            # "City, Country" / "City Country"
            parts = [p.strip() for p in re.split(r"[,/|]", raw) if p.strip()]
            for part in reversed(parts):
                pk = _norm(part)
                if pk in _COUNTRY_ALIASES:
                    country_code = _COUNTRY_ALIASES[pk]
                    break
            for part in parts:
                pk = _norm(part)
                if pk in _CITY_TO_COUNTRY:
                    city = part.strip()
                    country_code = country_code or _CITY_TO_COUNTRY[pk]
                    break
            # Token scan for known cities inside longer strings
            if not country_code:
                for city_key, code in sorted(_CITY_TO_COUNTRY.items(), key=lambda x: -len(x[0])):
                    if re.search(rf"\b{re.escape(city_key)}\b", key):
                        city = city_key.title()
                        country_code = code
                        break
            if not country_code:
                for alias, code in sorted(_COUNTRY_ALIASES.items(), key=lambda x: -len(x[0])):
                    if re.search(rf"\b{re.escape(alias)}\b", key):
                        country_code = code
                        break

    country_name = _COUNTRY_NAMES.get(country_code) if country_code else None
    # If only country known and raw looks like a city word, keep city = geo
    if country_code and not city and geo and _norm(geo) not in _COUNTRY_ALIASES:
        # geo may still be a city we didn't map — keep as city token for filtering
        if len(geo.split()) <= 4 and not remote:
            city = geo

    return {
        "raw": raw,
        "city": city,
        "country_code": country_code,
        "country_name": country_name,
        "is_remote": remote,
        "resolved": bool(country_code) or remote,
    }


def country_name_for_code(code: str | None) -> str | None:
    if not code:
        return None
    return _COUNTRY_NAMES.get(code.lower())
