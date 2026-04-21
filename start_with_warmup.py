#!/usr/bin/env python3
"""
Warmup script that starts the server and preloads the SpaCy model
"""
import subprocess
import time
import requests
import sys
import os

def wait_for_server(url, max_attempts=30):
    """Wait for server to be ready"""
    print("Waiting for server to start...")
    for i in range(max_attempts):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"✓ Server is ready! (attempt {i+1})")
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    print("✗ Server failed to start")
    return False

def warmup_server(url):
    """Call warmup endpoint to preload SpaCy"""
    print("Warming up SpaCy model...")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Warmup complete! Time taken: {data.get('time_taken', 0):.2f}s")
            return True
        else:
            print(f"⚠ Warmup returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠ Warmup failed: {e}")
        return False

if __name__ == "__main__":
    port = os.getenv("PORT", "8000")
    host = os.getenv("HOST", "0.0.0.0")
    
    print("="*60)
    print("Starting Talendeur CV Parser with Warmup")
    print("="*60)
    
    # Start server in background
    print(f"Starting server on {host}:{port}...")
    server_process = subprocess.Popen(
        ["uvicorn", "main_talendeur:app", "--host", host, "--port", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to be ready
    health_url = f"http://localhost:{port}/health"
    if wait_for_server(health_url):
        # Call warmup
        warmup_url = f"http://localhost:{port}/warmup"
        warmup_server(warmup_url)
        print("\n" + "="*60)
        print("Server is ready to accept requests!")
        print("="*60 + "\n")
        
        # Keep server running
        try:
            server_process.wait()
        except KeyboardInterrupt:
            print("\nShutting down...")
            server_process.terminate()
            server_process.wait()
    else:
        print("Failed to start server")
        server_process.terminate()
        sys.exit(1)
