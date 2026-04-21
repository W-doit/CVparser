from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from fastapi.responses import JSONResponse
import uvicorn
import os
import time

# Importing the CVParser class from your specific file 
# Note: We use the filename without the .py extension
from LinkedIn_PDF_Reader_Talendeur_for_microservices import CVParser
from response_transformer import transform_to_talendeur_format

# Initialize the FastAPI application
app = FastAPI(
    title="Talendeur CV Parser API",
    description="Microservice for extracting structured experience and enriched skills from LinkedIn PDFs",
    version="1.0.0"
)

# Configure CORS for React app integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate the parser once to load NLP models and dictionaries into memory
parser = CVParser()

# Warmup flag to track if SpaCy has been loaded
_warmed_up = False

@app.post("/parse-cv", tags=["Parser"])
async def extract_cv_data(file: UploadFile = File(...)):
    """
    Endpoint to receive a PDF file, process it through the extraction engine,
    and return a structured JSON response including enriched skill dimensions.
    """
    
    # 1. Format Validation: Ensure the uploaded file is a PDF
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are supported.")

    try:
        start_time = time.time()
        
        # 2. Read File Content: Extract raw bytes directly from the upload stream
        # This matches your 'parse(self, file_bytes)' method requirements
        pdf_bytes = await file.read()
        
        # 3. Core Processing: Trigger the 'parse' method from your specific class
        # This executes the segmentation, anchoring, and skill enrichment logic
        raw_data = parser.parse(pdf_bytes)
        
        # 4. Transform to Talendeur format
        structured_data = transform_to_talendeur_format(raw_data)
        
        # Log processing time
        elapsed = time.time() - start_time
        print(f"CV parsed in {elapsed:.2f}s")
        
        # 5. Success Response: Return the full dictionary as a JSON object
        return JSONResponse(content=structured_data, status_code=200)

    except ValueError as e:
        # Invalid PDF or parsing error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 6. Error Handling: Capture engine failures and return a 500 status code
        raise HTTPException(status_code=500, detail=f"Extraction Engine Error: {str(e)}")

@app.get("/health", tags=["System"])
def health_check():
    """
    Health check endpoint to verify the service is online and the model is loaded.
    """
    global _warmed_up
    
    # Warmup SpaCy on first health check to reduce first request latency
    if not _warmed_up:
        try:
            _ = parser.nlp  # Trigger lazy loading
            _warmed_up = True
        except:
            pass
    
    return {
        "status": "online", 
        "service": "Talendeur Parser",
        "nlp_loaded": parser.nlp is not None,
        "warmed_up": _warmed_up
    }

@app.get("/warmup", tags=["System"])
def warmup():
    """
    Warmup endpoint to preload SpaCy model. Call this after deployment to reduce first request latency.
    """
    global _warmed_up
    start_time = time.time()
    
    if not _warmed_up:
        try:
            # Force SpaCy model loading
            _ = parser.nlp
            if parser.nlp:
                # Run a dummy tokenization to fully initialize the pipeline
                parser.nlp("warmup test")
                _warmed_up = True
        except Exception as e:
            return {
                "status": "error",
                "message": f"Warmup failed: {str(e)}",
                "time_taken": time.time() - start_time
            }
    
    return {
        "status": "success",
        "message": "Parser warmed up and ready",
        "nlp_loaded": parser.nlp is not None,
        "time_taken": time.time() - start_time
    }

# --- Netlify Handler ---
handler = Mangum(app)

if __name__ == "__main__":
    # Start the server using Uvicorn on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

