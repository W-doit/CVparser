#!/bin/bash
# Startup script for Render deployment with automatic warmup

echo "Starting Talendeur CV Parser..."

# Start the FastAPI server in the background
uvicorn main_talendeur:app --host 0.0.0.0 --port ${PORT:-8000} &

# Get the PID of the server
SERVER_PID=$!

# Wait for server to be ready (max 30 seconds)
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:${PORT:-8000}/health > /dev/null 2>&1; then
        echo "Server is ready!"
        break
    fi
    sleep 1
done

# Call warmup endpoint to preload SpaCy
echo "Warming up SpaCy model..."
curl -s http://localhost:${PORT:-8000}/warmup > /dev/null 2>&1
echo "Warmup complete!"

# Wait for the server process
wait $SERVER_PID
