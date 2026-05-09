# 🚀 CV Parser API

LLM-powered FastAPI microservice that extracts and structures professional information from CV/resume PDFs into standardized JSON profiles.

## ✨ Features

- 🤖 **LLM-Powered Extraction** - Uses Groq's fast inference for accurate data extraction
- 📄 **Universal PDF Support** - Works with any CV format (not just LinkedIn)
- ⚡ **Fast Processing** - 3-5 seconds per CV with automatic retries
- 🔄 **Structured Output** - Consistent JSON format with profile, experience, education, skills, and more
- 🌐 **Production Ready** - Deployed on Render with CORS support for React apps
- 🆓 **Free Tier Available** - Groq offers 30 requests/minute for free

## 🏗️ Technical Stack

* **Framework:** FastAPI (Python 3.12+)
* **LLM Provider:** Groq (llama-3.1-8b-instant)
* **PDF Extraction:** pdfplumber
* **Retry Logic:** tenacity (exponential backoff)
* **Deployment:** Render
* **Serverless Ready:** Mangum adapter for AWS Lambda/Netlify

## 📂 Project Structure

```text
CVparser/
├── main_talendeur.py              # FastAPI app & endpoints
├── llm_parser.py                  # Groq LLM CV parser
├── response_transformer.py        # Legacy response formatter
├── requirements.txt               # Python dependencies
├── .env                          # Environment variables (API keys)
├── .gitignore                    # Git ignore rules
└── README.md                     # This file
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Groq API key (free at https://console.groq.com/)

### Local Development

1. **Clone and setup**
   ```bash
   git clone https://github.com/W-doit/CVparser.git
   cd CVparser
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Mac/Linux
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API key**
   
   Add to `.env` file:
   ```env
   GROQ_API_KEY=gsk_your_api_key_here
   ALLOWED_ORIGINS=*
   ```

4. **Run the server**
   ```bash
   python main_talendeur.py
   ```

5. **Test it**
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

---

## 📡 API Endpoints

### `POST /parse-cv`
Extracts structured data from a CV/resume PDF.

**Request:**
```bash
curl -X POST "http://localhost:8000/parse-cv" \
  -F "file=@your_cv.pdf"
```

**Response:**
```json
{
  "profile": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "location": "New York, USA",
    "headline": "Senior Data Scientist",
    "linkedin": "https://linkedin.com/in/johndoe",
    "summary": "Experienced data scientist..."
  },
  "workExperience": [
    {
      "title": "Senior Data Scientist",
      "company": "Tech Corp",
      "location": "New York, USA",
      "startDate": "2020-01",
      "endDate": "Present",
      "description": "Led data science initiatives...",
      "current": true
    }
  ],
  "education": [...],
  "skills": [...],
  "certifications": [...],
  "languages": [...],
  "skills_dimensions": {
    "leadership": 75,
    "technical": 90,
    "communication": 60,
    "analytical": 80,
    "creativity": 50
  }
}
```

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "online",
  "service": "Talendeur Parser (LLM-powered)",
  "parser_initialized": true,
  "groq_api_configured": true,
  "error": null
}
```

---

## 🌐 Deployment

### Deploy to Render

1. **Get Groq API Key**
   - Go to https://console.groq.com/
   - Sign up and create an API key
   - Copy the key (starts with `gsk_...`)

2. **Deploy to Render**
   - Connect your GitHub repo to Render
   - Add environment variable: `GROQ_API_KEY=gsk_your_key_here`
   - Render will auto-deploy on push

3. **Test Production**
   ```bash
   curl https://your-app.onrender.com/health
   ```

### Performance
- **PDF Extraction**: ~0.5-1s
- **LLM Inference**: ~2-4s  
- **Total**: 3-5 seconds per CV
- **Auto-retry**: 3 attempts with exponential backoff

---

## 🔗 React Integration

### Example Component

```javascript
import { useState } from 'react';

function CVUploader() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('https://your-app.onrender.com/parse-cv', {
        method: 'POST',
        body: formData,
      });
      
      const data = await res.json();
      setResult(data);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input type="file" accept=".pdf" onChange={handleUpload} />
      {loading && <p>Parsing CV...</p>}
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}
```

---

## 🛠️ How It Works

### 1. **PDF Text Extraction**
- Uses `pdfplumber` to extract text from PDFs
- Handles multi-page documents
- Preserves text structure and formatting

### 2. **LLM Processing**
- Sends extracted text to Groq's `llama-3.1-8b-instant` model
- Uses structured prompts to enforce JSON output
- Validates and parses LLM response

### 3. **Retry Logic**
- Automatic retry on API failures (3 attempts)
- Exponential backoff (2s → 4s → 8s)
- Handles rate limits gracefully

### 4. **Response Formatting**
- Validates required fields
- Calculates skills dimensions
- Returns consistent JSON structure

---

## 🧪 Testing

### Using Swagger UI
1. Go to http://localhost:8000/docs
2. Click `/parse-cv` → "Try it out"
3. Upload a PDF
4. Click "Execute"

### Using Test Script
```bash
python test_groq_parser.py http://localhost:8000
```

---

## 📋 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq API key for LLM inference | Yes |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | No (default: *) |

---

## 🐛 Troubleshooting

### Error: "Parser not initialized"
- **Cause**: Missing `GROQ_API_KEY`
- **Fix**: Add API key to `.env` file or environment variables

### Error: "Rate limit exceeded"
- **Cause**: Exceeded Groq free tier (30 req/min)
- **Fix**: Wait 60 seconds or upgrade Groq plan

### Error: "PDF extraction failed"
- **Cause**: Image-based PDF (scanned document)
- **Fix**: Use PDFs with selectable text

### Error: "Model decommissioned"
- **Cause**: Groq model no longer available
- **Fix**: Update `llm_parser.py` to use current model (check https://console.groq.com/docs/models)

---

## 📦 Dependencies

```txt
# Core Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
mangum==0.17.0

# PDF Processing
pdfplumber==0.10.3

# LLM Integration
groq>=0.11.0
tenacity==8.2.3

# Environment & HTTP
python-dotenv==1.0.0
python-multipart==0.0.6
```

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🤝 Contributing

Contributions welcome! Please open an issue or submit a PR.

---

## 📞 Support

For issues or questions:
- Open a GitHub issue
- Check Groq status: https://status.groq.com/
- Review Groq docs: https://console.groq.com/docs

---

**Built with ❤️ by the Wdoit Team**

