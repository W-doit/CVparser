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
* **LLM Provider:** Groq (`openai/gpt-oss-20b`, fallback `openai/gpt-oss-120b`)
* **PDF Extraction:** pdfplumber
* **Retry Logic:** tenacity (exponential backoff)
* **Deployment:** Render
* **Serverless Ready:** Mangum adapter for AWS Lambda/Netlify

## 📂 Project Structure

```text
CVparser/
├── main_talendeur.py              # FastAPI app & endpoints
├── llm_parser.py                  # Groq LLM CV parser + recommendations + job matching
├── job_sources/
│   └── linkedin.py                # LinkedIn MCP + Jina Reader job search
├── response_transformer.py        # Legacy response formatter
├── requirements.txt               # Python dependencies
├── .env                          # Environment variables (API keys)
├── .env.example                  # Env template (incl. LinkedIn MCP / Jina)
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

### `POST /job-matches`
Find LinkedIn openings for a jobseeker profile and return AI-ranked matches.

Uses these backends (accumulate until enough results):

1. **LinkedIn MCP** (`LINKEDIN_MCP_URL` / `mcporter`) — optional; needs always-on host + dedicated LinkedIn login
2. **Jina Reader** on public LinkedIn jobs search URLs — brittle; may 403
3. **Adzuna** — free developer key (`ADZUNA_APP_ID` + `ADZUNA_APP_KEY`)
4. **Arbeitnow** — free public board API, no key

**Request:**
```bash
curl -X POST "http://localhost:8000/job-matches" \
  -H "Content-Type: application/json" \
  -d "{\"profile\":{\"headline\":\"Project Manager\",\"work\":[{\"title\":\"PM\"}]},\"location\":\"Remote\",\"limit\":10}"
```

**Response (shape):** `{ summary, queries, backend, matches: [{ id, title, company, location, url, score, why_fit, gaps }] }`

Also available: `POST /gap-analysis`, `POST /career-foresight` (profile recommendations).

---

## LinkedIn job matching setup (ops)

Use a **dedicated throwaway LinkedIn account** — never a personal main account. Automation can trigger limits or bans.

**Hosting note:** Live LinkedIn MCP (Option A) needs an always-on host with a persistent browser session (VPS / co-located frontend+backend). It will **not** work on Netlify or typical serverless/PaaS (Render free, etc.). Use **Option B (Jina)** on those platforms for now; add Option A later when both apps run on a real instance.

### Option A — linkedin-scraper-mcp / mcp-server-linkedin

```bash
# Install (example)
pip install linkedin-scraper-mcp
# or: uvx mcp-server-linkedin@latest

# Login once with a visible browser (dedicated account)
linkedin-scraper-mcp --login --no-headless
# or: uvx mcp-server-linkedin@latest --login

# Run MCP over HTTP (example port)
linkedin-scraper-mcp --transport streamable-http --port 8001
```

Then set on the CVparser host:

```env
LINKEDIN_MCP_URL=http://localhost:8001
# Optional simple JSON bridge if you wrap MCP yourself:
# LINKEDIN_MCP_BRIDGE_URL=http://localhost:8002
```

If you use [mcporter](https://github.com/nicobailon/mcporter) (Agent-Reach style), register the LinkedIn MCP and leave `mcporter` on `PATH`. Set `LINKEDIN_DISABLE_MCPORTER=true` to skip that path.

### Option B — Jina only (no LinkedIn login)

Leave MCP unset. The service falls back to:

```env
JINA_READER_PREFIX=https://r.jina.ai/
```

Jina can read public LinkedIn job pages but results are more limited and may change when LinkedIn blocks bots.

### Option C — Adzuna + Arbeitnow (recommended free fallbacks)

**Adzuna** (broader coverage; free developer key):

1. Register at https://developer.adzuna.com/
2. Set on the CVparser host:

```env
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key
# Optional default country when location is empty:
ADZUNA_COUNTRY=gb
```

**Arbeitnow** needs no config — it is always tried when earlier backends return too few jobs.

### Redeploy

After pulling these changes, redeploy CVparser (e.g. Render) and confirm Talendeur `VITE_CV_PARSER_API_URL` points at that service. The Matches tab calls `POST {VITE_CV_PARSER_API_URL}/job-matches`.

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
- Sends extracted text to Groq's `openai/gpt-oss-20b` model (large CVs → `openai/gpt-oss-120b`)
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

### Error: "Rate limit exceeded" (HTTP 429)
- **Cause**: Exceeded a Groq free tier limit — the daily cap (1,000 req/day) is the one most likely to bind first
- **Fix**: Wait for the window to reset, or upgrade to the Groq Developer plan (see below)

### Error: "PDF extraction failed"
- **Cause**: Image-based PDF (scanned document)
- **Fix**: Use PDFs with selectable text

### Error: "Model decommissioned"
- **Cause**: Groq retired the old Llama IDs (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) on 2026-08-16
- **Fix**: Defaults are now `openai/gpt-oss-20b` / `openai/gpt-oss-120b`. Override with `GROQ_MODEL` / `GROQ_FALLBACK_MODEL`, or check https://console.groq.com/docs/models and https://console.groq.com/docs/deprecations

---

## ⚠️ Groq API Limits & Scaling

All LLM calls (CV parsing, gap analysis, career foresight, job match ranking) go through the same `GROQ_API_KEY`. Groq enforces limits **per organisation**, not per API key — creating extra keys does not increase capacity.

### Free tier limits (2026)

| Limit | Value |
|---|---|
| Requests per minute (RPM) | 30 |
| Tokens per minute (TPM) | 6,000–12,000 depending on model |
| **Requests per day (RPD)** | **1,000** (resets midnight UTC) |
| Tokens per day (TPD) | 100,000–500,000 |

The **daily request cap (1,000 RPD)** is the first limit likely to be hit in production. Each user action that calls an LLM endpoint (parse CV, gap analysis, foresight, job match) consumes one request. At ~4–5k tokens per call, tokens are generally not the bottleneck.

When any limit is exceeded the API returns **HTTP 429**. The CVparser already has exponential-backoff retry logic (tenacity) for transient 429s, but a sustained daily cap will fail all calls until midnight UTC.

### Upgrading to paid (Developer plan)

**No code changes are required.** Simply:

1. Go to [console.groq.com/settings/billing](https://console.groq.com/settings/billing)
2. Add a payment method and switch to the **Developer plan**
3. Redeploy CVparser on Render — the same `GROQ_API_KEY` now has higher limits

Developer plan base limits: **1,000 RPM · 300,000 TPM · no hard daily cap**. Cost is pay-as-you-go (~$0.002–0.006 per typical Talendeur call depending on model).

### Monitor usage

Check live usage and per-model limits at: [console.groq.com/settings/limits](https://console.groq.com/settings/limits)

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

