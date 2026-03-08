# 🚀 CV Parser Microservice

A serverless FastAPI microservice that extracts and structures information from LinkedIn PDF resumes into standardized JSON professional profiles.

## 🏗️ Technical Architecture

* **Core Framework:** FastAPI (Python 3.13+)
* **NLP Engine:** SpaCy (`en_core_web_sm`)
* **PDF Extraction:** `pdfplumber` for coordinate-based text reading
* **Serverless Adapter:** Mangum (for Netlify/AWS Lambda compatibility)
* **Deployment:** Netlify Functions

## 📂 Project Structure

```text
CVparser/
├── api/
│   ├── main_talendeur.py                              # API Endpoints & Mangum Handler
│   └── LinkedIn_PDF_Reader_Talendeur_for_microservices.py # Core NLP Engine
├── netlify.toml                                       # Deployment configuration
├── requirements.txt                                   # Python dependencies
├── runtime.txt                                        # Python version
├── .env.example                                       # Environment variables template
├── .gitignore                                         # Git ignore rules
└── README.md                                          # Documentation
```

## 🚀 Quick Start

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd CVparser
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Mac/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

4. **Run the development server**
   ```bash
   cd api
   python main_talendeur.py
   ```

5. **Access the API**
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## 📡 API Endpoints

### POST /parse-cv
Extracts structured data from a LinkedIn PDF resume.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: PDF file (field name: `file`)

**Response:**
```json
{
  "profile": {
    "name": "John Doe",
    "title": "Senior Data Scientist",
    "email": "john@example.com",
    "phone": "+1234567890",
    "location": "New York, USA"
  },
  "summary_for_wordcloud": "...",
  "experience": [...],
  "education": [...],
  "skills": {
    "hard_skills": [...],
    "soft_skills": [...]
  },
  "languages": [...],
  "certifications": [...]
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "online",
  "service": "Talendeur Parser",
  "nlp_loaded": true
}
```

## 🌐 Deployment to Netlify

### Prerequisites
- Netlify account
- Git repository linked to Netlify

### Steps

1. **Push your code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Connect to Netlify**
   - Go to [Netlify](https://app.netlify.com)
   - Click "Add new site" → "Import an existing project"
   - Select your repository

3. **Configure build settings**
   - Build command: `pip install -r requirements.txt && python -m spacy download en_core_web_sm`
   - Publish directory: `.`
   - Functions directory: `api`

4. **Set environment variables** (optional)
   - Go to Site settings → Environment variables
   - Add `ALLOWED_ORIGINS` with your React app URL

5. **Deploy**
   - Netlify will automatically deploy your site
   - Your API will be available at: `https://your-site-name.netlify.app`

## 🔗 React Integration

### Example: File Upload Component

```javascript
import { useState } from 'react';

function CVUploader() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setLoading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('https://your-api-url.netlify.app/parse-cv', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Error parsing CV:', error);
      alert('Failed to parse CV');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input 
        type="file" 
        accept=".pdf" 
        onChange={handleFileUpload}
        disabled={loading}
      />
      {loading && <p>Processing...</p>}
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}

export default CVUploader;
```

### Environment Configuration

Create a `.env` file in your React project:

```env
REACT_APP_API_URL=http://localhost:8000
# or for production:
# REACT_APP_API_URL=https://your-api-url.netlify.app
```

Use in your code:

```javascript
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const response = await fetch(`${API_URL}/parse-cv`, {
  method: 'POST',
  body: formData,
});
```


## 🧠 Core Logic & Extraction Heuristics

The engine goes beyond simple anchor detection, utilizing a hybrid approach that combines spatial coordinates with text-pattern analysis to classify data types.

### 1. Spatial Segmentation (Anchors)
The engine identifies primary headers (e.g., *Experience*) by scanning the vertical ($y$-axis) position. This creates "Contextual Buckets" where the data is contained.

### 2. Format-Based Classification (Heuristics)
Inside each segment, the parser uses a mix of specialized accessory functions to determine the nature of each text line:
* **Entity Validation**: Functions like `is_company()` or `is_location()` analyze font styles and known patterns to distinguish a Company Name from a Job Role.

* **Country & Location Mapping**: Integrates `pycountry` and custom dictionaries to normalize geographical data, even when formatted inconsistently in the PDF.

* **Type Identification**: Distinguishes between "Body Text" (descriptions) and "Metadata" (dates, locations, or titles) based on their horizontal indentation and proximity to other elements.

### 3. Multi-Dimensional Skill Mapping
Extracted tokens are cross-referenced against a thematic taxonomy to group professional capabilities into strategic dimensions (Leadership, Strategic Thinking, etc.), providing a more holistic view of the candidate than a flat list of keywords.

## 🛠️ Main Functions

### `CVParser.extract_text_with_coordinates()`
The primary data extractor. It captures text strings along with their precise $(x, y)$ coordinates to preserve the document's original structure.

### `CVParser.parse_experience()`
A state-aware function that iterates through the Experience block. It uses the accessory functions to decide if a line represents a new company entry or a continuation of a previous role.

### `accessory_functions` (Validation Logic)
A suite of helper functions (including Regex and dictionary lookups) that act as "validators" to confirm:
* **Dates**: Normalizing varied formats (e.g., "Present", "2023", "Oct-22").
* **Contact Data**: Identifying emails and phone numbers via pattern recognition.
* **Geographical Entities**: Mapping cities and countries to standard ISO codes.

## 🌐 Deployment Logic
This service uses a netlify.toml configuration to:

Automated Build: Install dependencies and download SpaCy models during the build phase.

Serverless Execution: Convert the FastAPI app into a Lambda-compatible function via Mangum.

