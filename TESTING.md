# Testing Instructions

## ❌ Local Testing Issue
There's a Python package version conflict (SpaCy/Pydantic) in your local environment. 

## ✅ Solution: Test on Netlify Directly

Since your code is already deployed, you can test it right now:

### Method 1: Using Netlify's API Endpoint

1. **Find your Netlify URL:**
   - Go to https://app.netlify.com
   - Find your CVparser deployment
   - Copy the URL (e.g., `https://your-site-name.netlify.app`)

2. **Test with curl:**
   ```bash
   curl -X POST "https://your-site-name.netlify.app/parse-cv" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@Profile.pdf"
   ```

3. **Or use the interactive docs:**
   - Visit: `https://your-site-name.netlify.app/docs`
   - Click on `/parse-cv` endpoint
   - Click "Try it out"
   - Upload Profile.pdf
   - Click "Execute"

### Method 2: Using Postman

1. Create a new POST request
2. URL: `https://your-site-name.netlify.app/parse-cv`
3. Body → form-data
4. Key: `file` (type: File)
5. Value: Select Profile.pdf
6. Send

### Method 3: Using React (Your App)

```javascript
const formData = new FormData();
formData.append('file', profilePdfFile);

const response = await fetch('https://your-site-name.netlify.app/parse-cv', {
  method: 'POST',
  body: formData,
});

const data = await response.json();
console.log(data);
```

## Expected Response Structure

```json
{
  "profile": {
    "name": "John Doe",
    "headline": "Senior Developer",
    "email": "john@example.com",
    "phone": "+1234567890",
    "city": "New York",
    "country": "USA"
  },
  "experience": [
    {
      "company": "Company Name",
      "role": "Job Title",
      "start_date": "2020",
      "end_date": "Present",
      "location": "City, Country",
      "description": "..."
    }
  ],
  "education": [...],
  "skills": [...],
  "languages": [...],
  "certifications": [...]
}
```

## Local Testing (If you want to fix it)

```bash
# Create clean virtual environment
python -m venv venv
venv\Scripts\activate

# Install compatible versions
pip install fastapi==0.104.1 uvicorn pdfplumber spacy==3.5.0 pycountry python-multipart mangum

# Download model
python -m spacy download en_core_web_sm

# Run test
python test_parser.py
```

But honestly, **just test it on Netlify** - it's faster! 🚀
