#!/usr/bin/env python3

import subprocess
import time
import os
import sys
import webbrowser
import signal

def start_frontend():
    """Start the Svelte frontend development server"""
    os.chdir("testpilot")
    if os.name == 'nt':  # Windows
        return subprocess.Popen(["npm", "run", "dev", "--", "--host", "0.0.0.0"], 
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:  # Linux/Mac
        return subprocess.Popen(["npm", "run", "dev", "--", "--host", "0.0.0.0"], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def start_backend():
    """Start the Flask backend server"""
    if os.name == 'nt':  # Windows
        return subprocess.Popen(["python", "client_endpoint.py"], 
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:  # Linux/Mac
        return subprocess.Popen(["python", "client_endpoint.py"], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def main():
    print("Starting UI Testing Dashboard...")
    
    # Start the backend Flask server
    print("Starting Flask backend...")
    backend_process = start_backend()
    
    # Give the backend a moment to start
    time.sleep(2)
    
    # Start the frontend development server
    print("Starting Svelte frontend...")
    frontend_process = start_frontend()
    
    # Open the browser after a short delay
    time.sleep(3)
    webbrowser.open("http://localhost:5173")
    
    print("Application started! Access the dashboard at http://localhost:5173")
    print("Press Ctrl+C to shut down both servers...")
    
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        
        # Kill the processes
        if backend_process:
            if os.name == 'nt':  # Windows
                backend_process.terminate()
            else:
                os.kill(backend_process.pid, signal.SIGTERM)
        
        if frontend_process:
            if os.name == 'nt':  # Windows
                frontend_process.terminate()
            else:
                os.kill(frontend_process.pid, signal.SIGTERM)
        
        print("Application shut down successfully")

if __name__ == "__main__":
    main()
