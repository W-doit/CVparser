"""
LLM-based CV Parser using Groq API
Extracts structured information from CV text using LLM
"""
import os
import json
import re
from datetime import datetime
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import pdfplumber
import io


class GroqCVParser:
    """
    CV Parser using Groq's fast LLM inference
    """
    
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        
        self.client = Groq(api_key=api_key)
        # Using llama-3.1-8b-instant for fast, reliable extraction
        # Alternative: "llama-3.3-70b-versatile" for more complex CVs
        self.model = "llama-3.1-8b-instant"
    
    def _normalize_date(self, date_str):
        """
        Normalize dates to PostgreSQL-compatible YYYY-MM-DD format
        
        Rules:
        - "2022-04" or "April 2022" → "2022-04-01"
        - "2022" → "2022-01-01"
        - "2022-04-15" → "2022-04-15" (keep as is)
        - null/empty/invalid → null
        """
        if not date_str or date_str is None:
            return None
        
        # Convert to string and clean
        date_str = str(date_str).strip()
        
        # Check for "Present", "Current", etc.
        if date_str.lower() in ["present", "current", "actualidad", "presente", "now"]:
            return None
        
        # Pattern 1: Already full ISO format YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # Pattern 2: Year-Month only YYYY-MM
        match = re.match(r'^(\d{4})-(\d{2})$', date_str)
        if match:
            year, month = match.groups()
            return f"{year}-{month}-01"
        
        # Pattern 3: Just year YYYY
        match = re.match(r'^(\d{4})$', date_str)
        if match:
            year = match.group(1)
            return f"{year}-01-01"
        
        # Pattern 4: Month name + year (e.g., "April 2022", "Apr 2022")
        month_names = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02',
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09', 'sept': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12'
        }
        
        # Try "Month YYYY" or "Month, YYYY"
        for month_name, month_num in month_names.items():
            pattern = rf'\b{month_name}[,\s]+(\d{{4}})\b'
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                year = match.group(1)
                return f"{year}-{month_num}-01"
        
        # Pattern 5: Extract year if nothing else matches
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', date_str)
        if year_match:
            year = year_match.group(1)
            return f"{year}-01-01"
        
        # Unable to parse - return null
        return None
        
    def extract_text_from_pdf(self, file_bytes):
        """
        Extract text from PDF using pdfplumber
        Optimized for LinkedIn-style 2-column layouts
        """
        full_text = ""
        
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract all text from page
                    page_text = page.extract_text(layout=True) or ""
                    
                    if page_text:
                        # Clean up excessive whitespace
                        page_text = '\n'.join(line.strip() for line in page_text.split('\n') if line.strip())
                        full_text += f"\n--- Page {page_num} ---\n{page_text}\n"
            
            if not full_text.strip():
                raise ValueError("No text could be extracted from PDF. It may be image-based or corrupted.")
            
            return full_text.strip()
        
        except Exception as e:
            raise ValueError(f"PDF extraction failed: {str(e)}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def _call_groq_api(self, prompt, temperature=0.1):
        """
        Call Groq API with retry logic
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CV/resume parser. Extract information accurately and return valid JSON only. Never add explanations outside the JSON structure."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            max_tokens=4000,
            response_format={"type": "json_object"}  # Force JSON output
        )
        
        return response.choices[0].message.content
    
    def parse(self, file_bytes):
        """
        Main parsing method - extracts structured data from CV
        """
        # Step 1: Extract text from PDF
        cv_text = self.extract_text_from_pdf(file_bytes)
        
        # Step 2: Build structured prompt
        prompt = self._build_extraction_prompt(cv_text)
        
        # Step 3: Call LLM with retry logic
        try:
            response_text = self._call_groq_api(prompt)
            parsed_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {str(e)}")
        except Exception as e:
            raise ValueError(f"LLM parsing failed: {str(e)}")
        
        # Step 4: Validate and return
        return self._validate_and_structure(parsed_data)
    
    def _build_extraction_prompt(self, cv_text):
        """
        Build comprehensive extraction prompt for the LLM
        """
        return f"""Extract all information from this CV/resume and return a valid JSON object.

CV TEXT:
{cv_text[:6000]}

Return ONLY valid JSON with this EXACT structure and field names:
{{
  "profile": {{
    "firstName": "First name only (max 55 chars)",
    "surname": "Last name only (max 55 chars)",
    "email": "email@example.com",
    "bio": "Professional summary/about section text",
    "headline": "Current job title or professional headline"
  }},
  "workExperience": [
    {{
      "job_title": "Full job title",
      "company": "Company name",
      "location": "City, Country",
      "start_date": "YYYY-MM-DD or YYYY-MM",
      "end_date": "YYYY-MM-DD or YYYY-MM or null",
      "still_work_here": true
    }}
  ],
  "education": [
    {{
      "institution": "University/School name",
      "qualification_type": "PhD/Master/Bachelor/Associate/Certificate/Diploma/High School",
      "subject": "Field of study or major",
      "start_date": "YYYY-MM-DD or YYYY-MM",
      "end_date": "YYYY-MM-DD or YYYY-MM or null",
      "still_studying": false
    }}
  ],
  "skills": [
    "Python",
    "Leadership",
    "Data Analysis"
  ],
  "certifications": [
    {{
      "course_name": "Full certification name",
      "certification_type": "Project Management/Data Analysis/Technology/Leadership/Business Strategy/Marketing/Design/Finance/HR/Other",
      "date_attained": "YYYY-MM-DD or YYYY-MM",
      "details": "Issuing organization or additional info (max 100 chars)"
    }}
  ],
  "languages": [
    {{
      "language": "Language name",
      "proficiency": "Native/Fluent/Advanced/Intermediate/Basic"
    }}
  ]
}}

CRITICAL RULES:
1. PROFILE:
   - Split full name into firstName and surname
   - bio is the summary/about/objective section
   
2. WORK EXPERIENCE:
   - Use "job_title" NOT "title"
   - Use "start_date" and "end_date" NOT "startDate" or "endDate"
   - Use "still_work_here" NOT "current"
   - If still working: still_work_here=true AND end_date=null
   - If not working: still_work_here=false AND end_date must have a date
   - NEVER use "Present" or "Current" - use null for end_date
   - Dates in YYYY-MM-DD or YYYY-MM format
   
3. EDUCATION:
   - Use "qualification_type" NOT "degree"
   - Try to standardize qualification_type to: PhD, Master, Bachelor, Associate, Certificate, Diploma, or High School
   - Use "subject" for field of study
   - If still studying: still_studying=true AND end_date=null
   
4. SKILLS:
   - Return array of strings, NOT objects
   - Include both technical and soft skills
   - No duplicates
   
5. CERTIFICATIONS:
   - Use "course_name" NOT "name"
   - Use "date_attained" NOT "date"
   - certification_type must be one of: Project Management, Data Analysis, Technology, Leadership, Business Strategy, Marketing, Design, Finance, HR, Other
   - details is optional (max 100 chars)

Extract ALL work experiences chronologically (most recent first).
Use null (not "null" string) for missing values.
Return ONLY the JSON, no explanations."""
    
    def _validate_and_structure(self, parsed_data):
        """
        Validate LLM response and ensure required structure
        """
        # Ensure all required top-level keys exist
        required_keys = ["profile", "workExperience", "education", "skills", "certifications", "languages"]
        for key in required_keys:
            if key not in parsed_data:
                parsed_data[key] = [] if key != "profile" else {}
        
        # === PROFILE VALIDATION ===
        if not parsed_data["profile"]:
            parsed_data["profile"] = {}
        
        profile = parsed_data["profile"]
        
        # Ensure required profile fields
        profile_defaults = {
            "firstName": "",
            "surname": "",
            "email": None,
            "bio": "",
            "headline": ""
        }
        
        for key, default in profile_defaults.items():
            if key not in profile:
                profile[key] = default
        
        # Handle legacy "name" field if present (split into firstName/surname)
        if "name" in profile and profile["name"]:
            name_parts = profile["name"].strip().split(maxsplit=1)
            if not profile.get("firstName"):
                profile["firstName"] = name_parts[0] if name_parts else ""
            if not profile.get("surname") and len(name_parts) > 1:
                profile["surname"] = name_parts[1]
            del profile["name"]
        
        # Truncate firstName and surname to 55 chars
        profile["firstName"] = (profile.get("firstName") or "")[:55]
        profile["surname"] = (profile.get("surname") or "")[:55]
        
        # Handle legacy "summary" field
        if "summary" in profile and not profile.get("bio"):
            profile["bio"] = profile["summary"]
        if "summary" in profile:
            del profile["summary"]
        
        # === WORK EXPERIENCE VALIDATION ===
        for exp in parsed_data.get("workExperience", []):
            # Handle legacy field names
            if "title" in exp:
                exp["job_title"] = exp.pop("title")
            if "startDate" in exp:
                exp["start_date"] = exp.pop("startDate")
            if "endDate" in exp:
                exp["end_date"] = exp.pop("endDate")
            if "current" in exp:
                exp["still_work_here"] = exp.pop("current")
            
            # Ensure required fields
            if "job_title" not in exp:
                exp["job_title"] = "Not specified"
            if "company" not in exp:
                exp["company"] = "Unknown"
            if "still_work_here" not in exp:
                exp["still_work_here"] = False
            
            # Normalize dates to YYYY-MM-DD format
            exp["start_date"] = self._normalize_date(exp.get("start_date"))
            exp["end_date"] = self._normalize_date(exp.get("end_date"))
            
            # Ensure consistency: if still_work_here=true, end_date must be null
            if exp.get("still_work_here") is True:
                exp["end_date"] = None
            
            # If end_date is null and still_work_here not explicitly set, assume still working
            if exp.get("end_date") is None and "still_work_here" in exp:
                if exp["still_work_here"] is not False:
                    exp["still_work_here"] = True
            
            # Remove description field (not needed in output)
            if "description" in exp:
                del exp["description"]
        
        # === EDUCATION VALIDATION ===
        for edu in parsed_data.get("education", []):
            # Handle legacy field names
            if "degree" in edu:
                edu["qualification_type"] = edu.pop("degree")
            if "field" in edu:
                edu["subject"] = edu.pop("field")
            if "startDate" in edu:
                edu["start_date"] = edu.pop("startDate")
            if "endDate" in edu:
                edu["end_date"] = edu.pop("endDate")
            
            # Ensure required fields
            if "qualification_type" not in edu:
                edu["qualification_type"] = "Certificate"
            if "subject" not in edu:
                edu["subject"] = ""
            if "still_studying" not in edu:
                edu["still_studying"] = False
            
            # Standardize qualification types
            qual_lower = (edu.get("qualification_type") or "").lower()
            if "phd" in qual_lower or "doctorate" in qual_lower or "doctor" in qual_lower:
                edu["qualification_type"] = "PhD"
            elif "master" in qual_lower or "msc" in qual_lower or "mba" in qual_lower or "ma " in qual_lower:
                edu["qualification_type"] = "Master"
            elif "bachelor" in qual_lower or "bsc" in qual_lower or "ba " in qual_lower or "bs " in qual_lower:
                edu["qualification_type"] = "Bachelor"
            elif "associate" in qual_lower:
                edu["qualification_type"] = "Associate"
            elif "diploma" in qual_lower:
                edu["qualification_type"] = "Diploma"
            elif "high school" in qual_lower or "secondary" in qual_lower:
                edu["qualification_type"] = "High School"
            elif "certificate" in qual_lower or "certification" in qual_lower:
                edu["qualification_type"] = "Certificate"
            
            # Normalize dates to YYYY-MM-DD format
            edu["start_date"] = self._normalize_date(edu.get("start_date"))
            edu["end_date"] = self._normalize_date(edu.get("end_date"))
            
            # Ensure consistency: if still_studying=true, end_date must be null
            if edu.get("still_studying") is True:
                edu["end_date"] = None
            
            # Remove unnecessary fields
            for field in ["location", "grade"]:
                if field in edu:
                    del edu[field]
        
        # === SKILLS VALIDATION ===
        # Convert skills objects to simple string array if needed
        skills = parsed_data.get("skills", [])
        if skills and isinstance(skills[0], dict):
            # Extract skill names from objects
            parsed_data["skills"] = [
                skill.get("name") or skill.get("skill_name") or str(skill)
                for skill in skills
            ]
        
        # Remove duplicates while preserving order
        if parsed_data["skills"]:
            seen = set()
            unique_skills = []
            for skill in parsed_data["skills"]:
                if skill and skill not in seen:
                    seen.add(skill)
                    unique_skills.append(skill)
            parsed_data["skills"] = unique_skills
        
        # === CERTIFICATIONS VALIDATION ===
        for cert in parsed_data.get("certifications", []):
            # Handle legacy field names
            if "name" in cert:
                cert["course_name"] = cert.pop("name")
            if "date" in cert:
                cert["date_attained"] = cert.pop("date")
            if "issuer" in cert and "details" not in cert:
                cert["details"] = cert.pop("issuer")[:100]  # Max 100 chars
            
            # Ensure required fields
            if "course_name" not in cert:
                cert["course_name"] = "Unknown Certification"
            if "date_attained" not in cert:
                cert["date_attained"] = None
            if "details" not in cert:
                cert["details"] = ""
            
            # Normalize date to YYYY-MM-DD format
            cert["date_attained"] = self._normalize_date(cert.get("date_attained"))
            
            # Categorize certification type if not provided
            if "certification_type" not in cert or not cert["certification_type"]:
                cert["certification_type"] = self._categorize_certification(cert["course_name"])
            
            # Truncate details to 100 chars
            if cert["details"]:
                cert["details"] = cert["details"][:100]
            
            # Remove unnecessary fields
            for field in ["expiryDate", "credentialId"]:
                if field in cert:
                    del cert[field]
        
        # Add skills_dimensions
        parsed_data["skills_dimensions"] = self._calculate_skills_dimensions(parsed_data)
        
        return parsed_data
    
    def _categorize_certification(self, cert_name):
        """
        Categorize certification into standard types
        """
        if not cert_name:
            return "Other"
        
        cert_lower = cert_name.lower()
        
        # Technology
        if any(word in cert_lower for word in ["aws", "azure", "cloud", "python", "java", "data", "sql", 
                                                 "developer", "engineer", "programming", "software", 
                                                 "web", "cyber", "security", "ai", "ml", "machine learning"]):
            return "Technology"
        
        # Project Management
        if any(word in cert_lower for word in ["pmp", "project management", "agile", "scrum", "prince2", "kanban"]):
            return "Project Management"
        
        # Data Analysis
        if any(word in cert_lower for word in ["data analy", "analytics", "tableau", "power bi", "excel", "statistics"]):
            return "Data Analysis"
        
        # Leadership
        if any(word in cert_lower for word in ["leadership", "management", "executive", "coaching", "mentor"]):
            return "Leadership"
        
        # Business Strategy
        if any(word in cert_lower for word in ["strategy", "business", "mba", "finance", "accounting", "economics"]):
            return "Business Strategy"
        
        # Marketing
        if any(word in cert_lower for word in ["marketing", "seo", "digital", "social media", "advertising", "brand"]):
            return "Marketing"
        
        # Design
        if any(word in cert_lower for word in ["design", "ux", "ui", "adobe", "figma", "creative"]):
            return "Design"
        
        # Finance
        if any(word in cert_lower for word in ["cfa", "financial", "investment", "banking", "cpa"]):
            return "Finance"
        
        # HR
        if any(word in cert_lower for word in ["hr", "human resource", "recruitment", "talent"]):
            return "HR"
        
        return "Other"
    
    def _calculate_skills_dimensions(self, parsed_data):
        """
        Calculate professional dimensions based on extracted data
        Simple heuristic-based approach
        """
        dimensions = {
            "leadership": 0,
            "technical": 0,
            "communication": 0,
            "analytical": 0,
            "creativity": 0
        }
        
        # Analyze work experience for leadership indicators
        for exp in parsed_data.get("workExperience", []):
            job_title = (exp.get("job_title") or "").lower()
            
            if any(word in job_title for word in ["manager", "director", "lead", "head", "chief", "president", "vp"]):
                dimensions["leadership"] += 1
            
            if any(word in job_title for word in ["engineer", "developer", "architect", "technical", "analyst"]):
                dimensions["technical"] += 1
        
        # Analyze skills
        for skill in parsed_data.get("skills", []):
            skill_lower = skill.lower() if isinstance(skill, str) else ""
            
            if any(word in skill_lower for word in ["python", "java", "sql", "aws", "data", "code", "programming"]):
                dimensions["technical"] += 0.5
            
            if any(word in skill_lower for word in ["leadership", "management", "team"]):
                dimensions["leadership"] += 0.5
            
            if any(word in skill_lower for word in ["communication", "presentation", "writing"]):
                dimensions["communication"] += 0.5
            
            if any(word in skill_lower for word in ["analysis", "analytical", "research", "data"]):
                dimensions["analytical"] += 0.5
            
            if any(word in skill_lower for word in ["design", "creative", "ux", "ui"]):
                dimensions["creativity"] += 0.5
        
        # Normalize scores to 0-100 scale
        max_score = max(dimensions.values()) if dimensions.values() else 1
        if max_score > 0:
            dimensions = {k: min(100, int((v / max_score) * 100)) for k, v in dimensions.items()}
        
        return dimensions
