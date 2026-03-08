"""
Netlify Python Function Handler for FastAPI via Mangum
This is the entry point that Netlify calls
"""
import sys
import os

# Add root directory to Python path so we can import our modules
root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, root_dir)

# Now import the Mangum-wrapped FastAPI handler from main_talendeur
from main_talendeur import handler as app_handler

# Netlify will call this function
def handler(event, context):
    """
    Netlify function entry point
    Delegates to the Mangum handler which wraps our FastAPI app
    """
    return app_handler(event, context)
