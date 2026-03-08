"""
Response transformation utilities for Talendeur API
Converts parser output to match the required response structure
"""
import re
from datetime import datetime
from typing import Dict, Any, List, Optional


def transform_to_talendeur_format(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw parser output to Talendeur's required format
    """
    return {
        "profile": transform_profile(raw_data.get('profile', {}), raw_data.get('summary_for_wordcloud', {})),
        "education": transform_education(raw_data.get('education', [])),
        "workExperience": transform_work_experience(raw_data.get('experience', [])),
        "certifications": transform_certifications(raw_data.get('certifications', [])),
        "skills": transform_skills(raw_data.get('skills', []))
    }


def transform_profile(profile: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    """Transform profile data"""
    full_name = profile.get('name', '')
    first_name, surname = split_name(full_name)
    
    email = profile.get('email')
    # Validate email format
    if email and not is_valid_email(email):
        email = None
    
    bio = None
    if summary:
        bio = summary.get('raw_text') if isinstance(summary, dict) else str(summary)
    
    return {
        "firstName": truncate_string(first_name, 55),
        "surname": truncate_string(surname, 55),
        "email": email,
        "bio": bio,
        "headline": profile.get('headline')
    }


def transform_education(education_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform education records"""
    transformed = []
    
    for edu in education_list:
        qualification_type, subject = parse_degree(edu.get('degree', ''))
        start_date = normalize_date(edu.get('start_date'))
        end_date = normalize_date(edu.get('end_date'))
        still_studying = is_currently_active(edu.get('end_date'))
        
        transformed.append({
            "institution": edu.get('institution', ''),
            "qualification_type": qualification_type,
            "subject": subject,
            "start_date": start_date,
            "end_date": end_date,
            "still_studying": still_studying
        })
    
    return transformed


def transform_work_experience(experience_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform work experience records"""
    transformed = []
    
    for exp in experience_list:
        start_date = normalize_date(exp.get('start_date'))
        end_date = normalize_date(exp.get('end_date'))
        still_work_here = is_currently_active(exp.get('end_date'))
        
        transformed.append({
            "job_title": exp.get('role', ''),
            "company": exp.get('company', ''),
            "start_date": start_date,
            "end_date": end_date,
            "still_work_here": still_work_here
        })
    
    return transformed


def transform_certifications(cert_list: List[Any]) -> List[Dict[str, Any]]:
    """Transform certifications from strings to objects"""
    transformed = []
    
    for cert in cert_list:
        # If already a dict, use it; otherwise treat as string
        if isinstance(cert, dict):
            cert_name = cert.get('name', str(cert))
        else:
            cert_name = str(cert)
        
        cert_type = categorize_certification(cert_name)
        
        transformed.append({
            "course_name": cert_name,
            "certification_type": cert_type,
            "date_attained": None,  # Parser doesn't extract dates currently
            "details": truncate_string("", 100)  # Empty for now
        })
    
    return transformed


def transform_skills(skills_list: List[Any]) -> List[str]:
    """Transform skills to simple string array"""
    skills = []
    
    for skill in skills_list:
        if isinstance(skill, dict):
            skill_name = skill.get('skill_name', '')
        else:
            skill_name = str(skill)
        
        if skill_name:
            skills.append(skill_name)
    
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for skill in skills:
        if skill not in seen:
            seen.add(skill)
            deduped.append(skill)
    
    return deduped


# ==================== UTILITY FUNCTIONS ====================

def split_name(full_name: str) -> tuple[Optional[str], Optional[str]]:
    """Split full name into first name and surname"""
    if not full_name:
        return None, None
    
    parts = full_name.strip().split()
    if len(parts) == 0:
        return None, None
    elif len(parts) == 1:
        return parts[0], None
    else:
        # First part is first name, rest is surname
        return parts[0], ' '.join(parts[1:])


def is_valid_email(email: str) -> bool:
    """Validate email against required regex"""
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return bool(re.match(pattern, email))


def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Convert various date formats to ISO 8601 (YYYY-MM-DD)
    Handles: "2020", "Jan 2020", "January 2020", "Present", "Actualidad"
    """
    if not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    # Check if it's "Present" or similar
    if is_currently_active(date_str):
        return None
    
    # Try to parse the date
    try:
        # Case 1: Just a year "2020"
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01-01"
        
        # Case 2: Month + Year "Jan 2020" or "January 2020"
        month_year_match = re.match(r'^([A-Za-z]+)\.?\s+(\d{4})$', date_str)
        if month_year_match:
            month_str, year = month_year_match.groups()
            month_num = parse_month(month_str)
            if month_num:
                return f"{year}-{month_num:02d}-01"
        
        # Case 3: Already in YYYY-MM-DD format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # Fallback: Extract year if possible
        year_match = re.search(r'\d{4}', date_str)
        if year_match:
            return f"{year_match.group()}-01-01"
        
    except Exception:
        pass
    
    return None


def is_currently_active(date_str: Optional[str]) -> bool:
    """Check if the date indicates current/present status"""
    if not date_str:
        return False
    
    current_indicators = ['present', 'current', 'actualidad', 'presente', 'now']
    return str(date_str).lower().strip() in current_indicators


def parse_month(month_str: str) -> Optional[int]:
    """Convert month name/abbreviation to month number"""
    months = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    return months.get(month_str.lower().strip('.'))


def parse_degree(degree_str: str) -> tuple[str, str]:
    """Extract qualification type and subject from degree string"""
    if not degree_str:
        return 'Certificate', ''
    
    # Common degree type patterns
    degree_types = {
        'phd': 'PhD',
        'doctorate': 'PhD',
        'doctor': 'PhD',
        "master's": 'Master',
        'master': 'Master',
        'msc': 'Master',
        'mba': 'Master',
        'ma': 'Master',
        "bachelor's": 'Bachelor',
        'bachelor': 'Bachelor',
        'bsc': 'Bachelor',
        'ba': 'Bachelor',
        'associate': 'Associate',
        'diploma': 'Diploma',
        'certificate': 'Certificate',
        'certification': 'Certificate',
        'high school': 'High School',
        'secondary': 'High School'
    }
    
    qualification = 'Certificate'  # Default
    subject = degree_str
    
    degree_lower = degree_str.lower()
    for pattern, type_name in degree_types.items():
        if pattern in degree_lower:
            qualification = type_name
            # Try to extract subject after degree type
            if ',' in degree_str:
                parts = degree_str.split(',', 1)
                subject = parts[1].strip() if len(parts) > 1 else degree_str
            elif ' in ' in degree_lower:
                subject = degree_str.split(' in ', 1)[1].strip()
            elif ' of ' in degree_lower:
                subject = degree_str.split(' of ', 1)[1].strip()
            break
    
    return qualification, subject


def categorize_certification(cert_name: str) -> str:
    """Categorize certification into predefined types"""
    cert_lower = cert_name.lower()
    
    # Technology keywords
    tech_keywords = ['aws', 'azure', 'cloud', 'python', 'java', 'data', 'sql', 'developer', 
                     'engineer', 'programming', 'software', 'web', 'cyber', 'security', 'ai', 'ml']
    if any(kw in cert_lower for kw in tech_keywords):
        return "Technology"
    
    # Project Management keywords
    pm_keywords = ['pmp', 'project management', 'agile', 'scrum', 'prince2', 'kanban']
    if any(kw in cert_lower for kw in pm_keywords):
        return "Project Management"
    
    # Leadership keywords
    leadership_keywords = ['leadership', 'management', 'executive', 'coaching', 'mentor']
    if any(kw in cert_lower for kw in leadership_keywords):
        return "Leadership"
    
    # Business Strategy keywords
    strategy_keywords = ['strategy', 'business', 'mba', 'finance', 'accounting', 'economics']
    if any(kw in cert_lower for kw in strategy_keywords):
        return "Business Strategy"
    
    # Marketing keywords
    marketing_keywords = ['marketing', 'seo', 'digital', 'social media', 'advertising', 'brand']
    if any(kw in cert_lower for kw in marketing_keywords):
        return "Marketing"
    
    # Design keywords
    design_keywords = ['design', 'ux', 'ui', 'adobe', 'figma', 'creative']
    if any(kw in cert_lower for kw in design_keywords):
        return "Design"
    
    # Finance keywords
    finance_keywords = ['cfa', 'financial', 'investment', 'banking', 'cpa']
    if any(kw in cert_lower for kw in finance_keywords):
        return "Finance"
    
    # HR keywords
    hr_keywords = ['hr', 'human resource', 'recruitment', 'talent']
    if any(kw in cert_lower for kw in hr_keywords):
        return "HR"
    
    return "Other"


def truncate_string(text: Optional[str], max_length: int) -> Optional[str]:
    """Truncate string to max length"""
    if not text:
        return None
    
    text = str(text).strip()
    if len(text) > max_length:
        return text[:max_length - 3] + '...'
    return text if text else None