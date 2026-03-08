"""
Netlify Python Function Handler
"""
import sys
import os

# Add parent directory to path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from main_talendeur import handler

# Export the handler for Netlify
def handler(event, context):
    """Netlify function entry point"""
    from main_talendeur import handler as mangum_handler
    return mangum_handler(event, context)
