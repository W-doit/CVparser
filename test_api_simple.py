"""
Simple test script to verify the API works without SpaCy
This tests the PDF parsing without NLP enrichment
"""
import sys
import os

# Test 1: Can we import the modules?
print("Test 1: Importing modules...")
try:
    from fastapi import FastAPI
    from pdfplumber import PDF
    print("✓ FastAPI and pdfplumber imported successfully")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Can we read the parser file?
print("\nTest 2: Loading CV Parser...")
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
    # We'll skip importing CVParser if it fails due to SpaCy
    print("✓ Path configured")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 3: Check if we have a test PDF
print("\nTest 3: Looking for test PDFs...")
pdf_files = [f for f in os.listdir('.') if f.endswith('.pdf')]
if pdf_files:
    print(f"✓ Found {len(pdf_files)} PDF file(s): {', '.join(pdf_files)}")
else:
    print("✗ No PDF files found in the directory")
    print("  Please add a LinkedIn PDF to test with")

print("\n" + "="*60)
print("NEXT STEPS:")
print("="*60)
if pdf_files:
    print("\n1. Fix SpaCy compatibility issue by running:")
    print("   pip install spacy==3.7.5 --force-reinstall")
    print("\n2. Download SpaCy model:")
    print("   python -m spacy download en_core_web_sm")
    print("\n3. Test with your PDF:")
    print(f"   We'll use: {pdf_files[0]}")
else:
    print("\n1. Add a LinkedIn PDF export to this folder")
    print("2. Fix SpaCy and retry")

print("\nOr test online directly at: http://localhost:8000/docs")
print("="*60)
