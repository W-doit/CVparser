"""
Netlify Functions handler entry point
Re-exports the Mangum handler from main_talendeur
"""
from main_talendeur import handler

# This is what Netlify will call
# The handler is already the Mangum-wrapped FastAPI app
def handler(event, context):
    from main_talendeur import handler as mangum_handler
    return mangum_handler(event, context)
