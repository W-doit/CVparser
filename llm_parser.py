"""
LLM-based CV Parser using Groq API
Extracts structured information from CV text using LLM
"""
import os
import json
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

Return ONLY valid JSON with this exact structure:
{{
  "profile": {{
    "name": "Full name",
    "email": "email@example.com or null",
    "phone": "phone number or null",
    "location": "city, country or null",
    "headline": "professional headline/title",
    "linkedin": "LinkedIn URL or null",
    "summary": "professional summary or bio"
  }},
  "workExperience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "location": "City, Country or null",
      "startDate": "YYYY-MM or YYYY",
      "endDate": "YYYY-MM or YYYY or Present",
      "description": "Responsibilities and achievements",
      "current": true/false
    }}
  ],
  "education": [
    {{
      "degree": "Degree name",
      "field": "Field of study",
      "institution": "School/University name",
      "location": "City, Country or null",
      "startDate": "YYYY or null",
      "endDate": "YYYY or null",
      "grade": "GPA or honors or null"
    }}
  ],
  "skills": [
    {{
      "name": "Skill name",
      "category": "technical/soft/language"
    }}
  ],
  "certifications": [
    {{
      "name": "Certification name",
      "issuer": "Issuing organization",
      "date": "YYYY-MM or YYYY or null",
      "expiryDate": "YYYY-MM or null",
      "credentialId": "ID or null"
    }}
  ],
  "languages": [
    {{
      "language": "Language name",
      "proficiency": "Native/Fluent/Advanced/Intermediate/Basic"
    }}
  ]
}}

IMPORTANT:
- Extract ALL work experiences chronologically (most recent first)
- Include ALL skills mentioned
- Parse dates in YYYY-MM format when possible
- Use null for missing information
- Combine multi-line descriptions into single strings
- Return ONLY the JSON, no explanations"""
    
    def _validate_and_structure(self, parsed_data):
        """
        Validate LLM response and ensure required structure
        """
        # Ensure all required top-level keys exist
        required_keys = ["profile", "workExperience", "education", "skills", "certifications", "languages"]
        for key in required_keys:
            if key not in parsed_data:
                parsed_data[key] = [] if key != "profile" else {}
        
        # Ensure profile has required fields
        if not parsed_data["profile"]:
            parsed_data["profile"] = {}
        
        profile_defaults = {
            "name": "",
            "email": None,
            "phone": None,
            "location": None,
            "headline": "",
            "linkedin": None,
            "summary": ""
        }
        
        for key, default in profile_defaults.items():
            if key not in parsed_data["profile"]:
                parsed_data["profile"][key] = default
        
        # Add skills_dimensions (placeholder for now - can be enhanced)
        parsed_data["skills_dimensions"] = self._calculate_skills_dimensions(parsed_data)
        
        return parsed_data
    
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
            title = (exp.get("title", "") or "").lower()
            desc = (exp.get("description", "") or "").lower()
            
            if any(word in title for word in ["manager", "director", "lead", "head", "chief"]):
                dimensions["leadership"] += 1
            
            if any(word in desc for word in ["team", "manage", "lead", "mentor", "supervise"]):
                dimensions["leadership"] += 0.5
            
            if any(word in desc for word in ["develop", "code", "build", "engineer", "technical"]):
                dimensions["technical"] += 0.5
            
            if any(word in desc for word in ["present", "communicate", "collaborate", "coordinate"]):
                dimensions["communication"] += 0.5
            
            if any(word in desc for word in ["analyze", "data", "research", "optimize", "evaluate"]):
                dimensions["analytical"] += 0.5
            
            if any(word in desc for word in ["design", "creative", "innovate", "develop strategy"]):
                dimensions["creativity"] += 0.5
        
        # Normalize scores to 0-100 scale
        max_score = max(dimensions.values()) if dimensions.values() else 1
        if max_score > 0:
            dimensions = {k: min(100, int((v / max_score) * 100)) for k, v in dimensions.items()}
        
        return dimensions
