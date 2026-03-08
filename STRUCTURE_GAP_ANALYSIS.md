# CV Parser - Required vs Current Output Structure

## CRITICAL CHANGES NEEDED

### 1. ❌ Profile Structure Mismatch
**Current:**
```json
{
  "name": "John Doe",
  "headline": "...",
  "email": "...",
  "phone": "...",
  "city": "...",
  "country": "..."
}
```

**Required:**
```json
{
  "firstName": "John",
  "surname": "Doe",
  "email": "...",
  "bio": "...",
  "headline": "..."
}
```

**Changes:**
- ✅ Split `name` into `firstName` + `surname`
- ✅ Map `summary_for_wordcloud` to `bio`
- ❌ Remove `phone`, `city`, `country`, location fields

### 2. ❌ Education Structure Mismatch
**Current:**
```json
{
  "institution": "MIT",
  "degree": "Bachelor of Science, Computer Science",
  "start_date": "2018",
  "end_date": "2022"
}
```

**Required:**
```json
{
  "institution": "MIT",
  "qualification_type": "Bachelor",
  "subject": "Computer Science",
  "start_date": "2018-01-01",
  "end_date": "2022-01-01",
  "still_studying": false
}
```

**Changes:**
- ✅ Parse `degree` into `qualification_type` + `subject`
- ✅ Convert dates to ISO format (YYYY-MM-DD)
- ✅ Add `still_studying` boolean field

### 3. ❌ Work Experience Key Names
**Current:** `experience` → **Required:** `workExperience`
**Current:** `role` → **Required:** `job_title`

**Changes:**
- ✅ Rename array key
- ✅ Rename `role` to `job_title`
- ✅ Add `still_work_here` boolean
- ✅ Convert dates to ISO format
- ❌ Remove `location` and `description` fields

### 4. ❌ Certifications Structure
**Current:** Array of strings
```json
["AWS Certified Solutions Architect", "PMP Certification"]
```

**Required:** Array of objects
```json
[
  {
    "course_name": "AWS Certified Solutions Architect",
    "certification_type": "Technology",
    "date_attained": "2023-01-01",
    "details": ""
  }
]
```

**Changes:**
- ✅ Convert strings to objects
- ✅ Add `certification_type` categorization
- ✅ Extract/infer `date_attained`
- ✅ Add `details` field (max 100 chars)

### 5. ❌ Skills Format
**Current:** Array of enriched objects
```json
[
  {
    "skill_name": "Python",
    "type": "hard",
    "is_categorized": true,
    "leadership": false,
    ...
  }
]
```

**Required:** Simple string array
```json
["Python", "JavaScript", "Leadership"]
```

**Changes:**
- ✅ Flatten to simple string array
- ✅ Extract only `skill_name` from objects

## ACTION PLAN

We need to create a **response transformer** in the API that:
1. Transforms the parser output to match the required structure
2. Converts dates to ISO 8601 format
3. Adds required boolean fields
4. Validates email regex
5. Removes unnecessary fields

This will be added to `main_talendeur.py` as a transformation layer.
