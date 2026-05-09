from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from fastapi.responses import JSONResponse
import uvicorn
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the new LLM-based parser
from llm_parser import GroqCVParser

# Initialize the FastAPI application
app = FastAPI(
    title="Talendeur CV Parser API",
    description="LLM-powered microservice for extracting structured data from CVs using Groq",
    version="2.0.0"
)

# Configure CORS for React app integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize parser (will fail fast if GROQ_API_KEY is missing)
try:
    parser = GroqCVParser()
    _parser_initialized = True
    _init_error = None
except Exception as e:
    parser = None
    _parser_initialized = False
    _init_error = str(e)
    print(f"WARNING: Parser initialization failed: {e}")

@app.post("/parse-cv", tags=["Parser"])
async def extract_cv_data(file: UploadFile = File(...)):
    """
    Endpoint to receive a PDF file, extract text, and use LLM to parse structured data.
    Returns JSON with profile, work experience, education, skills, certifications, and languages.
    """
    
    # Check if parser is initialized
    if not _parser_initialized:
        raise HTTPException(
            status_code=503, 
            detail=f"Parser not initialized. Error: {_init_error}. Please check GROQ_API_KEY environment variable."
        )
    
    # 1. Format Validation: Ensure the uploaded file is a PDF
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are supported.")

    try:
        start_time = time.time()
        
        # 2. Read File Content: Extract raw bytes directly from the upload stream
        pdf_bytes = await file.read()
        
        # 3. Core Processing: Use LLM parser to extract and structure data
        structured_data = parser.parse(pdf_bytes)
        
        # Log processing time
        elapsed = time.time() - start_time
        print(f"CV parsed in {elapsed:.2f}s")
        
        # 4. Success Response: Return the full dictionary as a JSON object
        return JSONResponse(content=structured_data, status_code=200)

    except ValueError as e:
        # Invalid PDF or parsing error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 5. Error Handling: Capture engine failures and return a 500 status code
        raise HTTPException(status_code=500, detail=f"Extraction Engine Error: {str(e)}")

@app.get("/health", tags=["System"])
def health_check():
    """
    Health check endpoint to verify the service is online and Groq API is configured.
    """
    groq_key_set = bool(os.getenv("GROQ_API_KEY"))
    
    return {
        "status": "online" if _parser_initialized else "degraded", 
        "service": "Talendeur Parser (LLM-powered)",
        "parser_initialized": _parser_initialized,
        "groq_api_configured": groq_key_set,
        "error": _init_error if _init_error else None
    }

@app.get("/warmup", tags=["System"])
def warmup():
    """
    Warmup endpoint - not needed for LLM-based parser (kept for compatibility)
    """
    return {
        "status": "success",
        "message": "LLM parser is ready (no warmup needed)",
        "parser_initialized": _parser_initialized
    }

# --- Netlify Handler ---
handler = Mangum(app)

if __name__ == "__main__":
    # Start the server using Uvicorn on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

