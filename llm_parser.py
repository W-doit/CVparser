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
        # Groq production chat models (Llama 3.1/3.3 shut down 2026-08-16).
        # Overrides: GROQ_MODEL / GROQ_FALLBACK_MODEL — see console.groq.com/docs/models
        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b")
        # Token limits (conservative to account for prompt overhead)
        self.max_cv_chars_small = 3500  # ~900 tokens for CV text
        self.max_cv_chars_large = 10000  # For larger model
    
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

    def _looks_like_professional_certification(self, edu):
        """
        True when an education entry is actually a professional certification
        and should live under certifications[], not education[].
        """
        qual = (edu.get("qualification_type") or "").strip()
        institution = str(edu.get("institution") or "")
        subject = str(edu.get("subject") or "")
        text = f"{qual} {institution} {subject}".lower()

        # Clear academic degrees stay in education
        if qual in {"PhD", "Master", "Bachelor", "Associate", "High School"}:
            return False

        academic_degree = bool(
            re.search(
                r"\b(ph\.?d|doctorate|doctoral|masters?|bachelor|associate|"
                r"b\.?sc|m\.?sc|mba|m\.?eng|b\.?eng|undergraduate|licen[cs]iatura|grado|"
                r"high\s*school|secondary|a-?levels?)\b",
                text,
            )
        )
        academic_institution = bool(
            re.search(r"\b(university|universidad|college|école|schule|polytechnic|institute of technology)\b", text)
        )

        cert_signals = [
            "certification", "certified", "certificate", "professional certificate",
            "aws", "azure", "google cloud", "gcp", "coursera", "udemy", "udacity",
            "linkedin learning", "datacamp", "pluralsight", "pmp", "prince2",
            "scrum", "csm", "psm", "cisco", "comptia", "ccna", "ccnp", "cka",
            "ckad", "salesforce", "hubspot", "six sigma", "itil", "bootcamp",
            "nanodegree", "credential", "accreditat",
        ]
        has_cert_signal = any(signal in text for signal in cert_signals)

        if academic_degree and academic_institution and not has_cert_signal:
            return False

        # Explicit Certificate / Diploma without university framing → certifications
        if qual in {"Certificate", "Diploma"} and has_cert_signal:
            return True
        if qual == "Certificate" and not academic_institution:
            return True
        if has_cert_signal and not academic_degree:
            return True

        return False

    def _education_to_certification(self, edu):
        """Convert a misclassified education row into a certifications[] item."""
        course_name = (
            edu.get("subject")
            or edu.get("qualification_type")
            or "Professional Certification"
        )
        if edu.get("qualification_type") and edu.get("subject"):
            course_name = f"{edu.get('qualification_type')} - {edu.get('subject')}"

        details = (edu.get("institution") or "")[:100]
        date_attained = edu.get("end_date") or edu.get("start_date")

        return {
            "course_name": str(course_name).strip()[:200],
            "certification_type": self._categorize_certification(str(course_name)),
            "date_attained": date_attained,
            "details": details,
        }

    def _separate_certifications_from_education(self, parsed_data):
        """
        Post-process: move professional certs out of education into certifications.
        """
        education = parsed_data.get("education") or []
        certifications = parsed_data.get("certifications") or []
        if not isinstance(education, list):
            return parsed_data
        if not isinstance(certifications, list):
            certifications = []

        kept_education = []
        moved = []
        existing_names = {
            str(c.get("course_name") or "").strip().lower()
            for c in certifications
            if isinstance(c, dict)
        }

        for edu in education:
            if not isinstance(edu, dict):
                continue
            if self._looks_like_professional_certification(edu):
                cert = self._education_to_certification(edu)
                name_key = cert["course_name"].strip().lower()
                if name_key and name_key not in existing_names:
                    certifications.append(cert)
                    existing_names.add(name_key)
                    moved.append(cert["course_name"])
            else:
                kept_education.append(edu)

        if moved:
            print(f"Moved {len(moved)} item(s) from education to certifications: {moved}")

        parsed_data["education"] = kept_education
        parsed_data["certifications"] = certifications
        return parsed_data

    def _normalize_qualification_type(self, qualification, subject="", institution=""):
        """
        Map free-text degree wording to Talendeur's fixed qualification_type values.
        Also inspects subject/institution when qualification is blank.
        """
        ALLOWED = {
            "PhD", "Master", "Bachelor", "Associate",
            "Certificate", "Diploma", "High School",
        }

        raw = " ".join(
            part for part in [str(qualification or ""), str(subject or ""), str(institution or "")]
            if part
        ).strip()

        if not raw:
            return ""

        # Already a valid enum value
        if str(qualification or "").strip() in ALLOWED:
            return str(qualification).strip()

        text = raw.lower()
        # Normalize punctuation so B.Sc / B.Sc. / B Sc match
        compact = re.sub(r"[.\s]+", "", text)

        # Order matters: more specific first
        if re.search(r"\b(ph\.?d|dphil|doctorate|doctoral)\b", text) or "phd" in compact:
            return "PhD"
        if re.search(r"\b(m\.?sc|m\.?eng|m\.?phil|mba|m\.?a\b|masters?|postgraduate)\b", text) or any(
            token in compact for token in ("msc", "meng", "mphil", "mba", "master")
        ):
            return "Master"
        if re.search(
            r"\b(b\.?sc|b\.?eng|b\.?a\b|b\.?s\b|bachelors?|undergraduate|licen[cs]iatura|grado)\b",
            text,
        ) or any(token in compact for token in ("bsc", "beng", "bachelor", "undergrad")):
            return "Bachelor"
        if "associate" in text or "aas" in compact:
            return "Associate"
        if "diploma" in text:
            return "Diploma"
        if re.search(r"\b(high\s*school|secondary|a-?levels?|gcse)\b", text):
            return "High School"
        if re.search(r"\b(certificate|certification|cert\b)\b", text):
            return "Certificate"

        # If LLM already returned one of the allowed labels with different casing
        for label in ALLOWED:
            if label.lower() in text:
                return label

        # Keep original non-empty qualification for manual review rather than inventing Certificate
        original = str(qualification or "").strip()
        return original

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
    def _call_groq_api(self, prompt, temperature=0.1, model=None):
        """
        Call Groq API with retry logic
        """
        if model is None:
            model = self.model
            
        response = self.client.chat.completions.create(
            model=model,
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
            max_tokens=2500,  # Reduced to stay within limits
            response_format={"type": "json_object"}  # Force JSON output
        )
        
        return response.choices[0].message.content
    
    def parse(self, file_bytes):
        """
        Main parsing method - extracts structured data from CV
        """
        # Step 1: Extract text from PDF
        cv_text = self.extract_text_from_pdf(file_bytes)
        
        # Step 2: Determine best model and truncate text appropriately
        cv_length = len(cv_text)
        
        if cv_length > self.max_cv_chars_small:
            # Use larger model for long CVs
            model_to_use = self.fallback_model
            truncated_text = cv_text[:self.max_cv_chars_large]
        else:
            # Use fast model for normal CVs
            model_to_use = self.model
            truncated_text = cv_text[:self.max_cv_chars_small]
        
        # Step 3: Build structured prompt
        prompt = self._build_extraction_prompt(truncated_text)
        
        # Step 4: Call LLM with retry logic
        try:
            response_text = self._call_groq_api(prompt, model=model_to_use)
            parsed_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {str(e)}")
        except Exception as e:
            # If rate limit error with small model, try fallback
            if "rate_limit_exceeded" in str(e) and model_to_use == self.model:
                try:
                    # Reduce text size more aggressively and retry with same model
                    smaller_text = cv_text[:2000]
                    prompt = self._build_extraction_prompt(smaller_text)
                    response_text = self._call_groq_api(prompt, model=model_to_use)
                    parsed_data = json.loads(response_text)
                except Exception:
                    raise ValueError(f"LLM parsing failed: {str(e)}")
            else:
                raise ValueError(f"LLM parsing failed: {str(e)}")
        
        # Step 5: Validate and return
        return self._validate_and_structure(parsed_data)
    
    def _build_extraction_prompt(self, cv_text):
        """
        Build comprehensive extraction prompt for the LLM
        """
        return f"""Extract all information from this CV/resume and return a valid JSON object.

CV TEXT:
{cv_text}

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
   - CRITICAL: Each role MUST have its OWN company name taken only from that role's block in the CV
   - NEVER copy/reuse the company name from a previous or next role
   - If a role's company is unclear, set company to null (do NOT invent or copy another employer)
   - Include EVERY distinct role — do not drop the most recent job
   - Promotions at the same employer may share a company name; different employers must NOT
  
3. EDUCATION:
   - Use "qualification_type" NOT "degree"
   - qualification_type MUST be exactly one of: PhD, Master, Bachelor, Associate, Certificate, Diploma, High School
   - Infer from text like "B.Sc", "BSc", "BA", "M.Sc", "MBA", "Ph.D", "Doctorate", etc.
   - NEVER leave qualification_type empty if any degree wording is present
   - Do NOT default university degrees to Certificate
   - Use "subject" for field of study / major
   - Include "location" when available (City, Country)
   - If still studying: still_studying=true AND end_date=null
   - EDUCATION is ONLY for academic degrees / school programmes (university, college, high school)
   - Do NOT put AWS/Google/Microsoft/PMP/Scrum/Coursera/bootcamp/professional certificates in education

4. SKILLS:
   - Return array of strings, NOT objects
   - Include both technical and soft skills
   - No duplicates
   
5. CERTIFICATIONS:
   - Put ALL professional / industry credentials here (AWS, Azure, Google, Cisco, CompTIA, PMP, Scrum, Coursera certificates, LinkedIn Learning, Udacity, bootcamps, licenses)
   - Use "course_name" NOT "name"
   - Use "date_attained" NOT "date"
   - certification_type must be one of: Project Management, Data Analysis, Technology, Leadership, Business Strategy, Marketing, Design, Finance, HR, Other
   - details is optional (max 100 chars) — usually the issuing organization
   - NEVER duplicate the same item in both education and certifications

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
        work_experiences = parsed_data.get("workExperience", [])
        if not isinstance(work_experiences, list):
            work_experiences = []
            parsed_data["workExperience"] = work_experiences

        for exp in work_experiences:
            # Handle legacy field names
            if "title" in exp:
                exp["job_title"] = exp.pop("title")
            if "startDate" in exp:
                exp["start_date"] = exp.pop("startDate")
            if "endDate" in exp:
                exp["end_date"] = exp.pop("endDate")
            if "current" in exp:
                exp["still_work_here"] = exp.pop("current")
            
            # Ensure required fields — never invent a company from a neighbour role
            if "job_title" not in exp or not str(exp.get("job_title") or "").strip():
                exp["job_title"] = "Not specified"
            company_raw = exp.get("company")
            if company_raw is None or str(company_raw).strip() == "":
                exp["company"] = "Unknown"
            else:
                exp["company"] = str(company_raw).strip()
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

        # Keep every role that has a job title (company may be "Unknown")
        parsed_data["workExperience"] = [
            exp for exp in work_experiences
            if str(exp.get("job_title") or "").strip()
        ]
       
        # === EDUCATION VALIDATION ===
        for edu in parsed_data.get("education", []):
            # Handle legacy field names
            if "degree" in edu and not edu.get("qualification_type"):
                edu["qualification_type"] = edu.pop("degree")
            elif "degree" in edu:
                edu.pop("degree", None)
            if "field" in edu:
                edu["subject"] = edu.pop("field")
            if "major" in edu and not edu.get("subject"):
                edu["subject"] = edu.pop("major")
            elif "major" in edu:
                edu.pop("major", None)
            if "startDate" in edu:
                edu["start_date"] = edu.pop("startDate")
            if "endDate" in edu:
                edu["end_date"] = edu.pop("endDate")
            
            # Ensure required fields exist
            if "subject" not in edu or edu.get("subject") is None:
                edu["subject"] = ""
            if "still_studying" not in edu:
                edu["still_studying"] = False
            if "institution" not in edu or edu.get("institution") is None:
                edu["institution"] = ""
            
            # Infer + standardize qualification_type (never leave blank when degree words exist)
            edu["qualification_type"] = self._normalize_qualification_type(
                edu.get("qualification_type"),
                subject=edu.get("subject") or "",
                institution=edu.get("institution") or "",
            )
            
            # Normalize dates to YYYY-MM-DD format
            edu["start_date"] = self._normalize_date(edu.get("start_date"))
            edu["end_date"] = self._normalize_date(edu.get("end_date"))
            
            # Ensure consistency: if still_studying=true, end_date must be null
            if edu.get("still_studying") is True:
                edu["end_date"] = None
            
            # Keep location if present (used by Talendeur Education form)
            if "location" not in edu or edu.get("location") is None:
                edu["location"] = ""
            
            # Remove unused fields
            for field in ["grade", "gpa", "description"]:
                if field in edu:
                    del edu[field]

        # Move professional certificates mistakenly placed under education
        parsed_data = self._separate_certifications_from_education(parsed_data)
        
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

    def analyze_gap(self, target_role: str, target_organization=None, profile: dict | None = None):
        """
        Compare profile snapshot against a target role and return structured gap analysis.
        """
        profile = profile or {}
        org_line = f" at {target_organization}" if target_organization else ""

        prompt = f"""You are a career coach for Talendeur. Analyze how well this jobseeker profile fits the target role "{target_role}"{org_line}.

Return ONLY valid JSON with this exact shape:
{{
  "target_role": "{target_role}",
  "target_organization": {json.dumps(target_organization)},
  "summary": "2-3 sentence overview",
  "match_score": 0-100 integer,
  "strengths": ["string", ...],
  "gaps": [
    {{
      "area": "skills|experience|education|certifications|languages|other",
      "title": "short title",
      "detail": "specific gap",
      "severity": "high|medium|low"
    }}
  ],
  "recommendations": [
    {{
      "action": "specific actionable step",
      "why": "brief rationale",
      "effort": "quick win|short term|longer term"
    }}
  ]
}}

Profile data:
{json.dumps(profile, ensure_ascii=False)[:12000]}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON. Be specific, practical, and grounded in the profile data.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        return data

    def analyze_career_foresight(
        self,
        profile: dict | None = None,
        industry_preference: str | None = None,
        open_to_career_switch: bool = False,
    ):
        """
        Future-ready career guidance: strategic directions and upskilling for an AI-shaped job market.
        """
        profile = profile or {}
        industry_line = (
            f'The user indicated interest in the "{industry_preference}" industry/sector.'
            if industry_preference
            else "No specific industry preference was given — infer the best adjacent directions from their profile."
        )
        switch_line = (
            "The user is open to a meaningful career switch (not just a title change)."
            if open_to_career_switch
            else "Prefer additive upskilling and positioning within/adjacent to their current trajectory — avoid reckless pivots."
        )

        system_prompt = """You are Talendeur's senior career strategist. Your job is NOT generic career advice.

Context you must internalize:
- AI is compressing routine knowledge work, first-draft production, and shallow analysis.
- Durable employability comes from: domain judgment, orchestration of people/systems, accountability for outcomes, ethical AI use, and proof-of-work artifacts.
- Human strengths machines remain weak at: trust-building, negotiation, ambiguous problem framing, cross-functional leadership, taste, and context-specific quality control.
- Every recommendation MUST cite a specific signal from the user's profile data (role title, skill, certification, AI usage frequency, bio, etc.).
- Do NOT recommend "learn Python" or "get into AI" unless the profile clearly supports that pivot.
- Prefer depth in adjacent skills over random trendy pivots.
- Be honest if the profile is thin — say what to document first.
- Tone: direct, encouraging, specific. No buzzword soup. No listing tools without tying them to outcomes.

Output ONLY valid JSON. No markdown."""

        user_prompt = f"""Analyze this jobseeker's full Talendeur profile and produce a future-ready career guidance report for an AI-shaped labour market.

{industry_line}
{switch_line}

Return JSON with EXACTLY this structure:
{{
  "positioning_thesis": "2-3 sentences: where THIS person is strong today and what makes them hireable in the next 3-5 years",
  "readiness_score": 0-100 integer (future-ready employability based on profile evidence, not optimism),
  "strategic_directions": [
    {{
      "title": "direction name",
      "why_now": "why this direction matters in 2025-2030 with AI",
      "fit_to_background": "must reference specific profile evidence",
      "risk_if_ignored": "what happens if they stay on current path without adapting"
    }}
  ],
  "upskilling_roadmap": {{
    "quick_wins": [
      {{
        "action": "specific step doable in days/weeks",
        "why": "rationale tied to AI labour market",
        "profile_signal": "exact profile field or fact this builds on",
        "effort": "quick win"
      }}
    ],
    "three_to_six_months": [
      {{
        "action": "...",
        "why": "...",
        "profile_signal": "...",
        "effort": "short term"
      }}
    ],
    "twelve_months": [
      {{
        "action": "...",
        "why": "...",
        "profile_signal": "...",
        "effort": "longer term"
      }}
    ]
  }},
  "ai_leverage_moves": [
    {{
      "action": "how to use AI in THEIR role family — not generic ChatGPT tips",
      "why": "why this creates competitive advantage",
      "profile_signal": "what in their profile this connects to"
    }}
  ],
  "avoid_chasing": [
    "2-4 things this specific profile type should NOT waste time on"
  ]
}}

Rules:
- Provide 3-5 strategic_directions.
- Provide at least 2 items per upskilling_roadmap tier.
- Provide at least 3 ai_leverage_moves.
- ai_fluency and ai_tools in the profile indicate current AI adoption — build on or close gaps honestly.
- If AI fluency is low, prioritize visible, documented AI workflows over advanced technical paths.

Profile data:
{json.dumps(profile, ensure_ascii=False)[:14000]}
"""

        response = self.client.chat.completions.create(
            model=self.fallback_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=3500,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        return data

    def match_jobs(self, profile: dict | None, jobs: list[dict], preferences: dict | None = None):
        """
        Rank LinkedIn (or other) job openings against a jobseeker profile.
        Returns { matches: [...], summary: str }
        """
        profile = profile or {}
        jobs = jobs or []
        if not jobs:
            return {"matches": [], "summary": "No job openings were found to match against."}

        system_prompt = """You are Talendeur's job matching engine.
Score how well each opening fits THIS candidate's profile AND their stated preferences.
Be specific and honest. Prefer roles that leverage documented experience over wishful pivots.
When the candidate has stated preferences (role, format, intent, level, etc.), weight those heavily in scoring.
Output ONLY valid JSON. No markdown."""

        # Build preferences section
        prefs = preferences or {}
        pref_labels = {
            "role_title": "Preferred role/title",
            "opportunity_type": "Opportunity type wanted",
            "intent": "Intent/mode",
            "time_commitment": "Time commitment",
            "compensation": "Compensation expectation",
            "skill_relationship": "Skill relationship",
            "industry": "Domain/industry",
            "format": "Format (remote/hybrid/on-site)",
            "outcome": "Outcome sought",
            "level": "Seniority level",
        }
        prefs_text = ""
        if prefs:
            lines = [f"- {pref_labels.get(k, k)}: {v}" for k, v in prefs.items() if v]
            if lines:
                prefs_text = "\n\nCandidate preferences (use these to boost/penalise scores):\n" + "\n".join(lines)

        user_prompt = f"""Rank these job openings for the candidate.

Return JSON with EXACTLY this shape:
{{
  "summary": "1-2 sentence overview of fit across the set",
  "matches": [
    {{
      "id": "job id from input",
      "score": 0-100 integer,
      "why_fit": "2-3 sentences citing profile evidence and preference alignment",
      "gaps": ["short gap vs this role or preference mismatch", ...]
    }}
  ]
}}

Rules:
- Include every job id from the input (same ids).
- Sort matches by score descending.
- gaps: 0-4 items per job; empty array if strong fit.
- score 80+ = strong fit, 60-79 = plausible with gaps, below 60 = stretch.
- If a role clearly conflicts with stated preferences (e.g. on-site when candidate wants remote), lower the score and note it in gaps.

Candidate profile:
{json.dumps(profile, ensure_ascii=False)[:9000]}{prefs_text}

Job openings:
{json.dumps(jobs, ensure_ascii=False)[:11000]}
"""

        response = self.client.chat.completions.create(
            model=self.fallback_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=3500,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        return data
