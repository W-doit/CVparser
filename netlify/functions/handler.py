"""
Netlify Python Function Handler for FastAPI via Mangum
This is the entry point that Netlify calls
"""
# Import the Mangum-wrapped FastAPI handler from main_talendeur
# (all modules are now in the same directory)
from main_talendeur import handler as app_handler

# Netlify will call this function
def handler(event, context):
    """
    Netlify function entry point
    Delegates to the Mangum handler which wraps our FastAPI app
    """
    return app_handler(event, context)
