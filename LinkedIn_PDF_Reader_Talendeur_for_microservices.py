import spacy
import pycountry
import re
import pdfplumber
import io

class CVParser:
    """
    Stateless microservice engine for parsing LinkedIn PDF resumes.
    Extracts text and structures it into a clean JSON/Dictionary format.
    """
    
    def __init__(self):
        # Lazy load NLP model - only when needed
        self._nlp = None
        
        # Pre-compile frequently used regex patterns for better performance
        self._date_pattern = re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|\b\d{4}\b|Present|Actualidad|Presente', re.IGNORECASE)
        self._email_pattern = re.compile(r'([\w\.-]+@[\w\.-]+\.\w+)')
        self._phone_pattern = re.compile(r'(\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9})')
        self._page_noise_pattern = re.compile(r"\b(page|página|pg|pág)\.?\s*\d+(\s*(of|de|/)\s*\d+)?\b", re.IGNORECASE)
        
        # Initialize static reference dictionaries
        self.countries_names = self._get_all_countries()
        
        # Support both English and Spanish LinkedIn headers
        self.main_headers = [
            "Summary", "Extracto", "Resumen",  # Summary in EN/ES
            "Experience", "Experiencia",  # Experience in EN/ES
            "Education", "Educación", "Formación",  # Education in EN/ES
            "Volunteer Experience", "Voluntariado",  # Volunteer in EN/ES
            "Projects", "Proyectos"  # Projects in EN/ES
        ]
        self.side_bar_headers = [
            "Contact", "Contacto",  # Contact in EN/ES
            "Top Skills", "Skills", "Aptitudes", "Competencias",  # Skills in EN/ES
            "Languages", "Idiomas",  # Languages in EN/ES
            "Certifications", "Certificaciones", "Licencias y certificaciones"  # Certifications in EN/ES
        ]

        # Global dictionary of job title terms
        self.job_keywords = {
            'specialist', 'coordinator', 'scientist', 'director', 'executive', 
            'manager', 'analyst', 'developer', 'engineer', 'lead', 'head',
            'intern', 'consultant', 'architect', 'representative', 'expert',
            'officer', 'associate', 'user', 'experience', 'partner', 'founder',
            'president', 'vice', 'staff', 'trainee', 'instructor', 'professor',
            'data scientist', 'data analyst', 'data engineer', 'product manager',
            'project manager', 'software engineer', 'web developer', 'ux designer',
            'marketing manager', 'sales manager', 'business analyst', 'hr specialist',
            'financial analyst', 'operations manager', 'customer service representative',
            'user experience designer', 'product owner', 'scrum master', 'devops engineer',
            'user experience specialist', 'machine learning engineer', 'artificial intelligence specialist',
            'policy analyst', 'researcher', 'academic', 'lecturer', 'advisor', 'coach', 'trainer',
        }

        # Job title suffixes for pattern matching
        self.job_suffixes = ('ist', 'or', 'er', 'ant', 'ent')
        
        # Action verbs for experience parsing
        self.action_verbs = {'led', 'managed', 'developed', 'created', 'implemented', 'designed',
            'coordinated', 'organized', 'established', 'launched', 'built',
            'improved', 'increased', 'reduced', 'achieved', 'delivered',
            'oversaw', 'directed', 'supervised', 'trained', 'mentored',
            'analyzed', 'researched', 'identified', 'resolved', 'optimized',
            'collaborated', 'facilitated', 'advised', 'consulted', 'presented',
            'planned', 'executed', 'maintained', 'supported', 'assisted',
            'contributed', 'ensured', 'provided', 'conducted', 'performed',
            'leading', 'managing', 'developing', 'creating', 'implementing',
            'designing', 'coordinating', 'organizing', 'building', 'improving',
            'overseeing', 'directing', 'supervising', 'training', 'mentoring',
            'analyzing', 'researching', 'identifying', 'resolving', 'optimizing',
            'collaborating', 'facilitating', 'advising', 'consulting', 'presenting',
            'planning', 'executing', 'maintaining', 'supporting', 'assisting',
            'contributing', 'ensuring', 'providing', 'conducting', 'performing',
            'specializing', 'bridging', 'strategizing'} 

        self.hard_skills = ['Python', 'Java', 'C++', 'SQL', 'Machine Learning', 'Data Analysis',
            'Project Management', 'Cloud Computing', 'Cybersecurity', 'Web Development',
            'Data Visualization', 'Artificial Intelligence', 'DevOps', 'Mobile App Development',
            'Blockchain', 'UI/UX Design', 'Digital Marketing', 'Networking', 'Software Development',
            'React', 'Django', 'Flask', 'TensorFlow', 'Keras', 'Pandas', 'NumPy', 'Tableau','Data Quality',
            'Technical Requirements','Data Governance','Data Strategy','Data Architecture','Data Engineering','Data Science']
        
        self.soft_skills = ['Communication', 'Teamwork', 'Problem-solving', 'Time management',
            'Adaptability', 'Critical thinking', 'Leadership', 'Creativity', 
            'Interpersonal skills', 'Conflict resolution', 'Emotional intelligence',
            'Collaboration', 'Decision making', 'Stress management', 'Negotiation',
            'Networking', 'Public speaking', 'Active listening', 'Empathy', 'Work ethic',
            'Flexibility', 'Cultural awareness', 'Motivation', 'Patience','Personal Drive']
        
        self.proficiency_mapping = {
            'Native or Bilingual': 'Native',
            'Native': 'Native',
            'Bilingual': 'Native',
            'Full Professional': 'Fluent',
            'Professional Working': 'Advanced',
            'Professional': 'Advanced',
            'Limited Working': 'Intermediate',
            'Elementary': 'Basic',
            'Elementary Proficiency': 'Basic'
        }

        # Master Dictionary: Keys are Area Names, Values are lists of keywords
        self.cert_classification_data = {
            "IT & Data Science": ['python', 'sql', 'data', 'cloud', 'aws', 'azure', 'ai', 'bi', 'analytics', 'software', 'programming', 'cybersecurity', 'machine learning'],
            "Web Design & Creative": ['ux', 'ui', 'user experience', 'figma', 'adobe', 'photoshop', 'illustrator', 'web design', 'frontend', 'canvas', 'typography'],
            "Finance & Legal": ['cfa', 'finance', 'investment', 'banking', 'accounting', 'financial', 'cpa', 'risk', 'tax', 'audit', 'compliance', 'legal'],
            "Project Management": ['pmp', 'agile', 'scrum', 'prince2', 'kanban', 'lean', 'pmi', 'project management', 'product owner'],
            "Civil Service & Public Policy": ['public policy', 'governance', 'administration', 'diplomacy', 'relations', 'urban planning', 'government'],
            "NGOs & Social Impact": ['humanitarian', 'non-profit', 'ngo', 'grants', 'fundraising', 'social impact', 'sustainability', 'unicef', 'unesco'],
            "Marketing & Sales": ['marketing', 'seo', 'sem', 'ads', 'content', 'social media', 'growth', 'brand', 'sales', 'ventas', 'copywriting', 'hubspot', 'salesforce'],
            "Soft Skills & Leadership": ['leadership', 'coaching', 'communication', 'management', 'team', 'negotiation', 'active listening', 'soft skills', 'public speaking'],
            "Languages": ['english', 'spanish', 'french', 'german', 'portuguese', 'italian', 'chinese', 'toefl', 'ielts', 'cambridge']
        }
        
        # Expanded list of non-tech and tech issuers as anchor points
        self.certification_issuers = [
            # General & e-Learning
            "Coursera", "LinkedIn", "Udemy", "edX", "Skillshare", "Pluralsight", 
            
            # Business, Finance & Legal
            "CFA Institute", "ACCA", "FINRA", "Project Management Institute", "PMI",
            "Bloomberg", "AICPA", "IMA", "Harvard Business", "Wharton", "Yale",
            
            # Human Resources & Soft Skills
            "SHRM", "HRCI", "Dale Carnegie", "Toastmasters", "Gallup",
            
            # Marketing & Sales
            "HubSpot", "Salesforce", "Hootsuite", "Meta", "Google Ads", "Marketo",
            
            # Supply Chain, Logistics & Quality
            "APICS", "ASCM", "ASQ", "Lean Six Sigma", "ISO", "Council of Supply Chain",
            
            # Medical & Safety
            "American Heart Association", "OSHA", "Red Cross", "HIPAA",
            
            # Technology (Keep these for overlap)
            "Google", "Microsoft", "AWS", "Amazon", "IBM", "Oracle", "Cisco", "Tableau", "SAP"
        ]


        # Reference dictionary for professional dimensions
        self.dimensions_ref = {
            'business_acumen': ['business sense', 'business acumen', 'project management skills', 'strategic vision', 'vendor relationships', 'customer satisfaction', 'business expertise', 'actionable insights', 'stakeholder management abilities', 'risk management expertise', 'crucial insights'],
            'collaboration': ['collaborative approach', 'collaborated', 'staff development', 'compassionate', 'mentorship', 'coordinate', 'collaborative spirit', 'mentoring approach', 'collaborative mindset', 'collaborative leadership', 'cross-functional teams', 'willingness to mentor', 'team player', 'collaboration', 'diplomacy', 'cross-functional leadership skills'],
            'leadership': ['problem-solving skills', 'collaborative approach', 'decision-making abilities', 'staff development', 'mentorship', 'strategic vision', 'staff supervision', 'crisis situations', 'program development', 'program management', 'handle challenging situations', 'leadership abilities', 'coordinate', 'problem-solving abilities', 'showed initiative', 'staff coordination', 'campaign execution', 'collaborative leadership', 'stakeholder management abilities', 'proactive approach', 'ability to troubleshoot', 'cross-functional leadership skills', 'execution capabilities'],
            'innovation': ['innovative', 'trends', 'designed', 'creative approach', 'process improvement', 'digital trends', 'innovative thinking', 'creative vision', 'creative flair', 'digital transformation', 'creative', 'innovative approach'],
            'precision': ['attention to detail', 'detailed', 'diagnostic skills', 'thorough', 'expertise', 'investigative abilities', 'meticulous', 'organizational skills', 'optimization', 'efficiency', 'efficient', 'accurate', 'well-documented', 'proficient', 'high-quality', 'commitment to excellence', 'research capabilities', 'rigorous', 'rigorous methodology', 'analytical rigor', 'accuracy', 'optimize performance', 'methodical', 'data-driven', 'well-crafted', 'effective', 'lean processes'],
            'critical_thinking': ['analytical abilities', 'problem-solving skills', 'assessment skills', 'research skills', 'diagnostic skills', 'decision-making abilities', 'strategic vision', 'crisis situations', 'program development', 'program management', 'investigative abilities', 'organizational skills', 'optimization', 'problem-solving abilities', 'learning capacity', 'well-documented', 'complex problems', 'analytical mindset', 'translate complex data', 'research capabilities', 'intellectual curiosity', 'analytical rigor', 'strategic thinking', 'actionable insights', 'risk management expertise', 'crucial insights', 'ability to troubleshoot', 'data-driven', 'analytical approach'],
            'depth': ['comprehensive', 'complex', 'knowledge', 'research skills', 'diagnostic skills', 'thorough', 'commitment', 'expertise', 'investigative abilities', 'optimization', 'learning capacity', 'well-documented', 'complex problems', 'high-quality', 'translate complex data', 'deep', 'commitment to excellence', 'research capabilities', 'complex experiments', 'intellectual curiosity', 'analytical rigor', 'thoughtful', 'complex projects', 'risk management expertise', 'data-driven'],
            'commitment': ['dedication', 'commitment', 'staff development', 'mentorship', 'consistently', 'learning capacity', 'genuine passion', 'passion', 'reliable', 'trusted', 'confidence', 'reliability', 'enthusiasm', 'continuous learning'],
            'social_impact': ['advocacy skills', 'community participation', 'education', 'mentorship', 'funding', 'program development', 'mentoring approach'],
            'communication': ['advocacy skills', 'client communication', 'education', 'staff development', 'mentorship', 'staff supervision', 'program development', 'community relationships', 'vendor relationships', 'organizational skills', 'coordinate', 'client relationships', 'communication skills', 'staff coordination', 'customer satisfaction', 'communicate solutions', 'collaborative mindset', 'cross-functional teams', 'actionable insights', 'stakeholder management abilities', 'diplomacy', 'ability to communicate', 'customer service skills', 'ability to explain', 'interpersonal skills', 'cross-team'],
            'empathy': ['compassionate', 'mentorship', 'mentoring approach', 'constructive', 'team player', 'diplomacy', 'customer service skills', 'interpersonal skills'],
            'flexibility': ['adapt', 'cross-functional teams', 'versatility', 'ability to adapt', 'ability to incorporate client feedback', 'ability to incorporate feedback', 'team player', 'stakeholder management abilities', 'diplomacy', 'customer service skills', 'interpersonal skills', 'cross-team', 'adaptability', 'cross-functional leadership skills']
        }

        # Keywords to distinguish technical (hard) skills from behavioral (soft)
        self.hard_skills_keywords = ['python', 'sql', 'r ', 'excel', 'tableau', 'power bi', 'aws', 'data analysis', 'econometrics', 'finance', 'git', 'stata', 'machine learning']

    @property
    def nlp(self):
        """Lazy load SpaCy model only when actually needed, with optimized settings"""
        if self._nlp is None:
            try:
                # Load with disabled components for 3-5x faster processing
                # We disable parser and NER since we mainly use tokenization
                self._nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
            except OSError:
                self._nlp = None
                print("Warning: SpaCy model 'en_core_web_sm' is not loaded.")
        return self._nlp

    def parse(self, file_bytes):
        """
        Main orchestrator method. Receives a PDF as bytes and returns a structured dictionary.
        """
        # 1. Ingestion
        main_content, sidebar_content = self._extract_from_linkedin_pdf(file_bytes)
        if not main_content and not sidebar_content:
            raise ValueError("The PDF file is empty, corrupted, or image-based.")

        # 2. Segmentation
        main_sections, main_pre_header = self._segment_text(main_content, self.main_headers)
        sidebar_sections, sidebar_pre_header = self._segment_text(sidebar_content, self.side_bar_headers)

        # 3. Pipelines Processing
        parsed_profile = self._parse_profile(main_pre_header, sidebar_sections)
        parsed_summary = self._parse_summary(main_sections.get('Summary', ''))
        
        raw_exp_isolated = self._extract_experience_section_isolated(main_content)
        healed_exp_clean = self._clean_and_heal_experience(raw_exp_isolated)
        final_prepared_exp_text = self._heal_vertical_fragments_experience(healed_exp_clean)
        parsed_experience = self._parse_experience_section(final_prepared_exp_text)

        healed_edu_text = self._heal_fragmented_text(main_sections.get('Education', ''))
        parsed_education = self._parse_education_section(healed_edu_text)

        parsed_skills = self._parse_skills(sidebar_sections.get('Top Skills', '') or sidebar_sections.get('Skills', ''))
        parsed_languages = self._parse_languages(sidebar_sections.get('Languages', ''))
        
        raw_cert_text = sidebar_sections.get('Certifications', '')
        cert_lines = [l.strip() for l in raw_cert_text.split('\n') if l.strip()]
        if cert_lines and cert_lines[0].lower() == "certifications": 
            cert_lines.pop(0)
        parsed_certs = self._parse_certification_names(cert_lines)

        # 4. Final Delivery Structure
        return {
            'profile': parsed_profile,
            'summary_for_wordcloud': parsed_summary,
            'experience': parsed_experience,
            'education': parsed_education,
            'skills': parsed_skills,
            'languages': parsed_languages,
            'certifications': parsed_certs
        }

    # ==========================================
    # 1. INGESTION & SEGMENTATION
    # ==========================================

    def _extract_from_linkedin_pdf(self, file_bytes):
        main_content = ""
        sidebar_content = ""
        orphan_buffer = ""
        
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_width = page.width
                page_height = page.height
                
                left_bbox = (0, 0, page_width * 0.35, page_height)
                right_bbox = (page_width * 0.35, 0, page_width, page_height)
                
                # Use simpler extraction - layout parameter adds significant overhead
                left_text = page.within_bbox(left_bbox).extract_text(layout=False) or ""
                right_text = page.within_bbox(right_bbox).extract_text(layout=False) or ""

                if right_text:
                    # Use pre-compiled pattern
                    right_text = self._page_noise_pattern.sub('', right_text)
                    page_lines = [l.strip() for l in right_text.split('\n') if l.strip()]
                    
                    if page_lines:
                        if orphan_buffer:
                            page_lines.insert(0, orphan_buffer)
                            orphan_buffer = ""

                        last_chunk = page_lines[-3:]
                        has_date = any(self._date_pattern.search(l) for l in last_chunk)

                        if not has_date:
                            if len(page_lines[-1]) < 60:
                                orphan_buffer = page_lines.pop()
                                if page_lines and len(page_lines[-1]) < 60 and not self._date_pattern.search(page_lines[-1]):
                                    orphan_buffer = page_lines.pop() + "\n" + orphan_buffer
                        
                        main_content += "\n".join(page_lines) + "\n"

                if left_text:
                    sidebar_content += left_text + "\n"
            
            if orphan_buffer:
                main_content += orphan_buffer

            main_content = self._clean_linkedin_text(main_content)
            sidebar_content = self._clean_linkedin_text(sidebar_content)
            
            return main_content, sidebar_content

    def _clean_linkedin_text(self, text):
        if not text:
            return ""
        # Use pre-compiled pattern
        text = self._page_noise_pattern.sub('', text)
        
        linkedin_headers = [
            "Contact", "Summary", "Top Skills", "Experience", 
            "Education", "Certifications", "Languages", "Projects", "Honors-Awards"
        ]
        for header in linkedin_headers:
            pattern = r'(?:^|(?<!\n))(' + re.escape(header) + r')(?:[:\n\s]|$)'
            text = re.sub(pattern, r'\n\n\1\n', text, flags=re.IGNORECASE)
        
        # Use pre-compiled patterns
        text = self._email_pattern.sub(r'\n\1\n', text)
        text = self._phone_pattern.sub(r'\n\1\n', text)

        lines = [l.strip() for l in text.split('\n')]
        clean_text = "\n".join(lines)
        return re.sub(r'\n{3,}', '\n\n', clean_text).strip()

    def _segment_text(self, text, known_headers):
        if not text:
            return {}, ""
        lines = text.split('\n')
        sections = {}
        current_section = None
        current_content = []
        pre_header_content = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            combined_with_next = ""
            if i + 1 < len(lines):
                combined_with_next = f"{line} {lines[i+1].strip()}".lower()

            found_header = None
            if combined_with_next in [h.lower() for h in known_headers]:
                found_header = next(h for h in known_headers if h.lower() == combined_with_next)
                i += 1 
            elif line.lower() in [h.lower() for h in known_headers]:
                found_header = next(h for h in known_headers if h.lower() == line.lower())

            if found_header:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = found_header
                current_content = []
            else:
                if current_section is None:
                    pre_header_content.append(line)
                else:
                    current_content.append(line)
            i += 1

        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
            
        return sections, '\n'.join(pre_header_content).strip()

    # ==========================================
    # 2. PROFILE & CONTACT
    # ==========================================

    def _parse_profile(self, main_pre_header, side_bar_sections):
        profile = {
            'name': None, 'headline': None, 'city': None, 'region': None, 'country': None,
            'phone': None, 'email': None, 'linkedin_url': None, 'github_url': None,
            'portfolio_url': None, 'website_url': None
        }
        if main_pre_header:
            lines = [line.strip() for line in main_pre_header.split('\n') if line.strip()]
            if lines:
                profile['name'] = lines[0]
                if len(lines) >= 2:
                    location_line = lines[-1]
                    location_parts = [part.strip() for part in location_line.split(',')]
                    if len(location_parts) >= 3:
                        profile['city'] = location_parts[0]
                        profile['region'] = location_parts[1]
                        profile['country'] = location_parts[2]
                    elif len(location_parts) == 2:
                        profile['city'] = location_parts[0]
                        profile['country'] = location_parts[1]
                    elif len(location_parts) == 1:
                        profile['country'] = location_parts[0]

                if len(lines) >= 3:
                    headline_lines = lines[1:-1]
                    profile['headline'] = ' '.join(headline_lines).strip()
                else:
                    headline_lines = lines[1:]
                    profile['headline'] = ' '.join(headline_lines).strip()

        if 'Contact' in side_bar_sections:
            contact_text = side_bar_sections['Contact']
            emails = self._extract_emails(contact_text)
            phones = self._extract_phone_numbers(contact_text)
            urls = self._extract_urls(contact_text)

            if emails: profile['email'] = emails[0]  
            if phones: profile['phone'] = phones[0]  
            if urls['LinkedIn']: profile['linkedin_url'] = urls['LinkedIn'][0]
            if urls['GitHub']: profile['github_url'] = urls['GitHub'][0]
            if urls['Portfolio']: profile['portfolio_url'] = urls['Portfolio'][0]
            if urls['Personal Website']: profile['website_url'] = urls['Personal Website'][0]

        return profile

    def _extract_emails(self, text):
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return re.findall(email_pattern, text)

    def _extract_phone_numbers(self, text):
        phone_pattern = r'(\+?[\d\s\-\.\(\)]{8,20})'
        phone_numbers = re.findall(phone_pattern, text)
        phones = []
        for m in phone_numbers:
            clean_m = m.strip().rstrip(' (.-') 
            if sum(c.isdigit() for c in clean_m) >= 7:
                phones.append(clean_m)
        return phones

    def _extract_urls(self, text):
        url_pattern = r'((?:https?://|www\.)?[\w\d\-\.]+\.[\w]{2,}(?:/[\w\d\-\._\?\,\'/\\\+&%\$#\=~]*)?)'
        all_links = re.findall(url_pattern, text)
        urls = {"LinkedIn": [], "GitHub": [], "Portfolio": [], "Personal Website": []}
        email_domains = ['gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'icloud.com']
        
        for link in all_links:
            clean_link = link.strip().rstrip('.,(')
            if '@' in clean_link:
                continue
            if clean_link in email_domains or any(clean_link == f"www.{d}" for d in email_domains):
                continue

            link_lower = clean_link.lower()
            if 'linkedin.com' in link_lower:
                urls["LinkedIn"].append(clean_link)
            elif 'github.com' in link_lower:
                urls["GitHub"].append(clean_link)
            elif any(ext in link_lower for ext in ['.com', '.io', '.me', '.net', '.org']):
                urls["Personal Website"].append(clean_link)
        return urls

    # ==========================================
    # 3. SUMMARY 
    # ==========================================

    def _parse_summary(self, summary_text):
        if not summary_text:
            return ""
        clean_text = summary_text.replace('\n', ' ').strip()
        clean_text = re.sub(r'\s+', ' ', clean_text)
        return {
            "raw_text": clean_text,
            "word_count": len(clean_text.split())
        }

    # ==========================================
    # 4. EXPERIENCE PIPELINE 
    # ==========================================

    def _parse_experience_section(self, cleaned_text):
        if not cleaned_text: return []
        lines = [line.strip() for line in cleaned_text.split('\n') if line.strip()]
        date_indices = [idx for idx, line in enumerate(lines) if self._extract_experience_dates(line)]
        experience_list = []
        
        # STATE: Anchor for multi-role scenarios
        last_valid_company = "Unknown"
        
        for i, date_idx in enumerate(date_indices):
            company = "Unknown"
            role = "Not specified"
            
            # Smart lookup to avoid taking dates as company names
            if date_idx >= 1:
                role = lines[date_idx - 1]
                
                if date_idx >= 2:
                    potential_company = lines[date_idx - 2]
                    # If line -2 contains a date, skip it and look at -3
                    if self._extract_experience_dates(potential_company):
                        company = lines[date_idx - 3] if date_idx >= 3 else "Unknown"
                    else:
                        company = potential_company
                else:
                    # Case where only one line exists above the date
                    company = lines[date_idx - 1]
                    role = "Not specified"

            # --- MULTI-ROLE LOGIC START ---
            # If the detected company is actually a job title or it failed to find one, 
            # and we have a previous company stored, we inherit it.
            # We define what constitutes an "invalid" company name to trigger the anchor
            is_invalid_company = (
                company == "Unknown" or 
                self._is_job(company) or 
                self._is_description_line(company) or  # If it looks like a task
                len(company.split()) > 5               # If it's too long to be a name
            )

            if is_invalid_company and last_valid_company != "Unknown":
                # Rescue: use the previous company
                company = last_valid_company
            else:
                # Update anchor only if we found a solid, non-description name
                if not is_invalid_company:
                    last_valid_company = company
                    
            # --- MULTI-ROLE LOGIC END ---

            # Your original anchor and limit logic (Don't touch this, it's great)
            next_anchor = date_indices[i+1] if i+1 < len(date_indices) else len(lines)
            limit_of_description = next_anchor - 2 if i+1 < len(date_indices) else next_anchor
            content_block = lines[date_idx + 1 : limit_of_description]
            
            location = "Not specified"
            description_parts = []
            for line in content_block:
                if self._is_location_line(line):
                    location = line
                elif self._is_description_line(line) or self._is_job(line):
                    description_parts.append(line)
                else:
                    description_parts.append(line)

            date_info = self._extract_experience_dates(lines[date_idx])
            if date_info:
                experience_list.append({
                    "company": company,
                    "role": role,
                    "location": location,
                    "start_date": date_info[0].get('start'),
                    "end_date": date_info[0].get('end'),
                    "description": " ".join(description_parts).strip()
                })
        return experience_list

    def _extract_experience_section_isolated(self, full_text):
        # Support both English and Spanish section headers
        # Try English first
        start_match = re.search(r'\b(Work\s+)?Experience\b', full_text, re.IGNORECASE)
        # If not found, try Spanish
        if not start_match:
            start_match = re.search(r'\bExperiencia\b', full_text, re.IGNORECASE)
        
        if not start_match:
            return ""
        start_pos = start_match.end()
        # End patterns in both English and Spanish
        end_patterns = r'\n\s*\b(Education|Educación|Formación|Skills|Aptitudes|Competencias|Certifications|Certificaciones|Licencias y certificaciones|Languages|Idiomas|Projects|Proyectos|Volunteer|Voluntariado|Honors|Interests)\b'
        end_match = re.search(end_patterns, full_text[start_pos:], re.IGNORECASE)
        if end_match:
            return full_text[start_pos : start_pos + end_match.start()].strip()
        return full_text[start_pos:].strip()

    def _clean_and_heal_experience(self, raw_segment):
        if not raw_segment: return ""
        text = raw_segment.replace('·', '').replace('•', '').strip()
        healed = self._heal_fragmented_text_2(text)
        return healed

    def _heal_fragmented_text_2(self, text):
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        healed_lines = []
        months_pattern = (
            r'^(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?$'
        )
        i = 0
        while i < len(lines):
            current_line = lines[i]
            if re.match(months_pattern, current_line, re.IGNORECASE):
                potential_date = current_line
                offset = 1
                while i + offset < len(lines):
                    next_l = lines[i+offset]
                    if (re.match(r'^\d{4}$', next_l) or next_l.startswith('-') or 
                        'present' in next_l.lower() or 'actualidad' in next_l.lower() or
                        re.match(months_pattern, next_l, re.IGNORECASE) or
                        ('year' in next_l.lower() or 'month' in next_l.lower())):
                        potential_date += f" {next_l}"
                        offset += 1
                    else:
                        break
                healed_lines.append(potential_date)
                i += offset
            else:
                healed_lines.append(current_line)
                i += 1
        return "\n".join(healed_lines)

    def _heal_vertical_fragments_experience(self, text):
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        healed_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # --- INJECTION 1: THE SHIELD ---
            # If the line is definitively prose/description, skip all company logic.
            # This protects words like "ACNUR" from being extracted out of a sentence.
            if self._is_description_line(line):
                healed_lines.append(line)
                i += 1
                continue
            # -------------------------------

            # Usamos tus validadores modulares
            is_company_start = self._is_caps_company(line) or self._is_likely_company(line)
            
            prev_line_has_dot = False
            if i > 0 and healed_lines:
                prev_line_has_dot = healed_lines[-1].strip().endswith('.')

            # OVERRIDE: Si hay una fecha en las próximas 5 líneas, es una Empresa
            date_ahead = False
            for offset in range(1, 6):
                if i + offset < len(lines) and self._extract_experience_dates(lines[i + offset]):
                    date_ahead = True
                    break

            if is_company_start and (not prev_line_has_dot or date_ahead):
                fragment_buffer = [line]
                j = i + 1
                while j < len(lines) and j < i + 6:
                    next_line = lines[j]
                    
                    # --- INJECTION 2: THE BRAKE ---
                    # We stop grouping the job title if we hit a date, location, 
                    # or if the next line is clearly a long description.
                    if (self._extract_experience_dates(next_line) or 
                        self._is_location_line(next_line) or 
                        self._is_description_line(next_line)):
                        break
                    # ------------------------------
                    
                    fragment_buffer.append(next_line)
                    j += 1
                
                if len(fragment_buffer) > 1:
                    healed_lines.append(fragment_buffer[0]) 
                    healed_lines.append(" ".join(fragment_buffer[1:])) 
                    i = j
                else:
                    healed_lines.append(line)
                    i += 1
            else:
                healed_lines.append(line)
                i += 1
                
        return "\n".join(healed_lines)

    def _extract_experience_dates(self, text):
        clean_text = re.sub(r'\([^)]*\d+[^)]*\)', '', text).strip()
        pattern = r'((?:[A-Za-z]+\.?\s+)?\d{4})\s*[\s\-\–\—]\s*((?:[A-Za-z]+\.?\s+)?\d{4}|Present|Actualidad|Presente)'
        matches = re.findall(pattern, clean_text, re.IGNORECASE)
        results = []
        for m in matches:
            results.append({
                'start': m[0].strip(),
                'end': m[1].strip()
            })
        return results

    # ==========================================
    # 5. EDUCATION PIPELINE 
    # ==========================================

    def _parse_education_section(self, education_text):
        if not education_text:
            return []
        education_text = self._clean_education_raw_text(education_text)
        lines = [l.strip() for l in education_text.split('\n') if l.strip() and not re.search(r'Page \d+ of \d+', l, re.I)]
        date_indices = [idx for idx, line in enumerate(lines) if self._extract_linkedin_dates(line)]
        education_list = []
        last_processed_idx = -1
        
        for i, date_idx in enumerate(date_indices):
            date_line = lines[date_idx]
            date_info = self._extract_linkedin_dates(date_line)[0]
            block = lines[last_processed_idx + 1 : date_idx]
            extra_text = re.sub(r'\(.*?\)', '', date_line).replace('·', '').strip()
            if extra_text:
                block.append(extra_text)
                
            if block:
                institution = block[0]
                if len(block) > 1:
                    degree_part = block[1]
                    field_part = " ".join(block[2:]) if len(block) > 2 else ""
                    if field_part and field_part.lower() not in degree_part.lower():
                        degree = f"{degree_part}, {field_part}"
                    else:
                        degree = degree_part
                else:
                    degree = "Certification/Degree"
            else:
                institution = "Unknown Institution"
                degree = "Unknown Degree"

            education_list.append({
                "institution": institution,
                "degree": degree,
                "start_date": date_info.get('start'),
                "end_date": date_info.get('end')
            })
            last_processed_idx = date_idx
        return education_list

    def _heal_fragmented_text(self, text):
        lines = [l.strip() for l in text.split('\n')]
        healed_lines = []
        months_pattern = (
            r'^(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?$'
        )
        i = 0
        while i < len(lines):
            current_line = lines[i]
            if re.match(months_pattern, current_line, re.IGNORECASE):
                potential_date = current_line
                offset = 1
                if i + 1 < len(lines) and re.match(r'^\d{4}$', lines[i+1]):
                    potential_date += f" {lines[i+1]}"
                    offset += 1
                    if i + offset < len(lines):
                        next_l = lines[i+offset]
                        if next_l.startswith('-') or next_l.lower() in ['present', 'actualidad']:
                            potential_date += f" {next_l}"
                            offset += 1
                            if i + offset < len(lines) and re.match(r'^\d{4}$', lines[i+offset]):
                                potential_date += f" {lines[i+offset]}"
                                offset += 1
                if offset > 1:
                    healed_lines.append(potential_date)
                    i += offset
                    continue
            healed_lines.append(current_line)
            i += 1
        return "\n".join(healed_lines)

    def _clean_education_raw_text(self, text):
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        cleaned_lines = []
        for line in lines:
            if not line:
                continue
            if not cleaned_lines:
                cleaned_lines.append(line)
                continue
            last_line = cleaned_lines[-1]
            if last_line.endswith('(') or line.startswith(')') or last_line.endswith('·'):
                cleaned_lines[-1] = f"{last_line} {line}".strip()
            elif re.match(r'^(\d{4}|\-|–|—)', line) and not re.search(r'[a-zA-Z]', line):
                cleaned_lines[-1] = f"{last_line} {line}".strip()
            elif last_line.startswith('(') and not last_line.endswith(')'):
                cleaned_lines[-1] = f"{last_line} {line}".strip()
            else:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    # ==========================================
    # 6. SKILLS, LANGUAGES & CERTS 
    # ==========================================
    
    def _parse_skills(self, text):
        """
        Parses raw skill text, cleans it, and returns a list of enriched dimension-aware objects.
        """
        if not text: return []
        
        # Split by common separators (newline, comma, bullets)
        raw_list = re.split(r',|\n|•|·', text)
        clean_list = [s.strip() for s in raw_list if len(s.strip()) > 1]
        
        # Process each skill through the enrichment engine
        enriched_skills = [self._enrich_skill(s) for s in clean_list]
        
        return enriched_skills

    def _classify_skill(self, skill):
        skill_lower = skill.lower().strip()
        if any(hard.lower() in skill_lower for hard in self.hard_skills):
            return "hard"
        if any(soft.lower() in skill_lower for soft in self.soft_skills):
            return "soft"
        return "unknown"

    def _parse_languages(self, languages_text):
        if not languages_text: return []
        languages_list = []
        lines = languages_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or len(line) < 2: continue
            pattern = r'^([A-Za-z\s]+)\s*\(([^)]+)\)$'
            match = re.match(pattern, line)

            if match:
                lang_name = match.group(1).strip() 
                proficiency_raw = match.group(2).strip()
                level = self.proficiency_mapping.get(proficiency_raw, proficiency_raw)
                languages_list.append({'language': lang_name, 'proficiency_level': level})
            else:
                languages_list.append({'language': line, 'proficiency_level': None})
        return languages_list

    def _parse_certification_names(self, cert_lines):
        if not cert_lines: return []
        combined_names = []
        current_buffer = ""
        
        for line in cert_lines:
            line = line.strip()
            if not line: continue
            line_lower = line.lower()
            
            # Check if line is a date pattern (year in parentheses at end)
            is_date_only = re.match(r'^\s*\(?\s*\d{4}\s*\)?\s*$', line.strip())
            
            # If it's just a year/date, append it to current buffer and continue
            if is_date_only:
                if current_buffer:
                    current_buffer = f"{current_buffer} {line}"
                continue
            
            is_new_area = False
            for category_item in self.cert_classification_data:
                for kw in self.cert_classification_data[category_item]:
                    if kw.lower() in line_lower:
                        is_new_area = True
                        break
                if is_new_area: break
                
            is_issuer = any(issuer.lower() in line_lower for issuer in self.certification_issuers)
            
            # Start a new certification if we detect a keyword/issuer AND we have accumulated content
            if (is_new_area or is_issuer) and current_buffer != "":
                combined_names.append(current_buffer.strip())
                current_buffer = line 
            else:
                if current_buffer == "":
                    current_buffer = line
                else:
                    current_buffer = f"{current_buffer} {line}"
                    
        if current_buffer:
            combined_names.append(current_buffer.strip())
        return combined_names

    def _classify_certification_areas(self, full_text):
        text = full_text.lower()
        hits = {area: any(kw in text for kw in keywords) 
                for area, keywords in self.cert_classification_data.items()}
        found = any(hits.values())
        return hits, found

    # ==========================================
    # 7. SHARED UTILITIES 
    # ==========================================

    def _extract_linkedin_dates(self, text):
        # Use pre-compiled pattern for better performance
        matches = self._date_pattern.findall(text)
        if not matches:
            return []
        
        # Simple date extraction - if we found dates, return them
        return [{'start': text, 'end': text}] if matches else []

    def _is_location_line(self, text, is_first_line=False):
        clean_text = text.strip()
        if not clean_text: return False
        business_suffixes = {'solutions', 'services', 'group', 'ltd', 'inc', 'corp', 'sa', 'sl'}
        if any(suffix in clean_text.lower().split() for suffix in business_suffixes):
            return False
        if is_first_line and ',' not in clean_text: return False
        if ',' in clean_text:
            parts = [p.strip().lower() for p in clean_text.split(',')]
            if any(p in self.countries_names for p in parts): return True
        return clean_text.lower() in self.countries_names

    def _is_country(self, text):
        clean_text = text.strip().lower()
        if clean_text in self.countries_names:
            return True
        for c in self.countries_names:
            if clean_text == c or (len(clean_text) > 4 and clean_text in c):
                return True
        return False

    def _get_all_countries(self):
        countries = set()
        for country in pycountry.countries:
            countries.add(country.name.lower())
            if hasattr(country, 'official_name'):
                countries.add(country.official_name.lower())
        manual_fixes = {'tanzania', 'spain', 'usa', 'uk', 'netherlands', 'uae', 'catalonia', 'barcelona'}
        countries.update(manual_fixes)
        return countries
    def _is_action_line(self, text):
        if not text: return False
        words = text.strip().split()
        if not words: return False
        first_word = re.sub(r'^[^a-zA-Z]+', '', words[0]).lower()
        return first_word in self.action_verbs

    def _is_description_line(self, text):
        if not text or not text.strip(): return False
        clean_text = text.strip()
        words = clean_text.split()
        num_words = len(words)
        if num_words >= 10: return True
        if num_words >= 6:
            return clean_text.endswith('.') or self._is_action_line(clean_text)
        if num_words >= 3:
            return clean_text.endswith('.') and self._is_action_line(clean_text)
        return False

    def _is_job(self, text):
        if not text: return False
        clean_text = text.lower().strip()
        words = clean_text.split()
        if any(keyword in words for keyword in self.job_keywords):
            return True
        if any(word.endswith(self.job_suffixes) for word in words if len(word) > 3):
            return True
        return False

    def _is_likely_company(self, text):
        clean = text.strip()
        if not clean or clean.endswith('.'):
            return False
        
        # EXCLUSION: If the line contains a date, it is NOT a company
        # The order is company,role and then date, so if we have a date, we know for sure this line is not a company name.
        if self._extract_experience_dates(clean):
            return False
            
        if self._is_location_line(clean) or self._is_country(clean):
            return False
            
        return clean[0].isupper()

    def _is_caps_company(self, text):
        clean = text.strip()
        # Ensure it's not a date and is uppercase
        if self._extract_experience_dates(clean):
            return False
        return clean.isupper() and len(clean) > 2
    
    def _enrich_skill(self, skill_name):
        """
        Maps a skill to professional dimensions and identifies if it's Hard or Soft.
        Returns a dictionary prepared for a Pandas DataFrame.
        """
        skill_clean = skill_name.lower().strip()
        
        # 1. Classification logic (Hard vs Soft)
        is_hard = any(hw in skill_clean for hw in self.hard_skills_keywords)
        skill_type = "hard" if is_hard else "soft"

        # 2. Dimensions Logic (Boolean mapping)
        dimensions_map = {dim: False for dim in self.dimensions_ref.keys()}
        found_any = False
        
        for dimension, keywords in self.dimensions_ref.items():
            for kw in keywords:
                if kw.lower() in skill_clean:
                    dimensions_map[dimension] = True
                    found_any = True
                    break # Optimization: stop at first match for this dimension
        
        # 3. Create a flat record for easy DataFrame ingestion
        record = {
            "skill_name": skill_name,
            "type": skill_type,
            "is_categorized": found_any
        }
        record.update(dimensions_map) # Flatten all booleans into the main record
        
        return record

# ==========================================
# LOCAL TESTING ENVIRONMENT 
# ==========================================
if __name__ == "__main__":
    import json
    
    # Change this to the path of your test PDF
    TEST_PDF_PATH = "Profile (4).pdf" 
    
    print("Initiating CVParser Test Environment...")
    
    try:
        parser = CVParser()
        with open(TEST_PDF_PATH, "rb") as f:
            pdf_bytes = f.read()
            
        print("PDF loaded into memory. Starting extraction...")
        result_json = parser.parse(pdf_bytes)
        
        print("\nExtraction Successful! Output:\n")
        print(json.dumps(result_json, indent=2, ensure_ascii=False))
        
    except FileNotFoundError:
        print(f"Error: Could not find the file '{TEST_PDF_PATH}'. Please update the path.")
    except Exception as e:
        print(f"Pipeline Error: {e}")