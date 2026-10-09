# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Startup script for 3080 pool Ollama instances.

Starts 8 Ollama instances on ports 11434-11441 with qwen3:8b model.
Run this on the 3080 box (TJ1: 100.124.236.23) at startup.

Usage: python scripts/start_3080_pool.py
"""
import subprocess
import sys
import time
from pathlib import Path

# Configuration
PORTS = [11434, 11435, 11436, 11437, 11438, 11439, 11440, 11441]
MODEL = "qwen3:8b"
OLLAMA_CMD = "ollama"  # Assume ollama is in PATH

def start_ollama_instance(port: int):
    """Start an Ollama instance on the given port."""
    print(f"Starting Ollama on port {port}...")
    
    # Set environment variables for this instance
    env = {
        **dict(os.environ),
        'OLLAMA_HOST': f'127.0.0.1:{port}',
        'OLLAMA_KEEP_ALIVE': '-1',  # Keep models loaded forever
        'OLLAMA_NUM_CTX': '32768'   # Context window limit
    }
    
    try:
        # Start ollama serve in background
        proc = subprocess.Popen(
            [OLLAMA_CMD, 'serve'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        
        # Wait a moment for startup
        time.sleep(5)
        
        # Check if process is still running
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"  FAILED to start on port {port}")
            print(f"    stdout: {stdout.decode()[-200:]}")
            print(f"    stderr: {stderr.decode()[-200:]}")
            return False
        
        print(f"  Started on port {port} (PID: {proc.pid})")
        
        # Warm up the model with a small request
        time.sleep(10)  # Give more time for full startup
        warmup_result = subprocess.run([
            'curl', '-s', '-m', '30',
            f'http://127.0.0.1:{port}/api/generate',
            '-d', f'{{"model": "{MODEL}", "prompt": "Hello", "stream": false}}'
        ], capture_output=True, text=True, timeout=35)
        
        if warmup_result.returncode == 0:
            print(f"  Warmed up {MODEL} on port {port}")
        else:
            print(f"  WARNING: Failed to warm up {MODEL} on port {port}")
        
        return True
        
    except Exception as e:
        print(f"  ERROR starting on port {port}: {e}")
        return False

def check_port_available(port: int) -> bool:
    """Check if a port is available."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0  # Port is available if connection failed
    except Exception:
        return True  # Assume available if check failed

def main():
    print("Starting 3080 pool Ollama instances...")
    print(f"Ports: {PORTS}")
    print(f"Model: {MODEL}")
    print()
    
    success_count = 0
    
    for i, port in enumerate(PORTS):
        print(f"[{i+1}/{len(PORTS)}] Port {port}")
        
        # Check if port is already in use
        if not check_port_available(port):
            print(f"  Port {port} already in use, skipping")
            continue
        
        # Start instance
        if start_ollama_instance(port):
            success_count += 1
            # Stagger startup to avoid overwhelming the system
            if i < len(PORTS) - 1:  # Don't sleep after the last one
                print(f"  Sleeping 30s before next instance...")
                time.sleep(30)
        else:
            print(f"  Failed to start on port {port}")
    
    print()
    print(f"Startup complete: {success_count}/{len(PORTS)} instances started")
    
    if success_count == 0:
        print("ERROR: No instances started successfully")
        sys.exit(1)
    elif success_count < len(PORTS):
        print("WARNING: Some instances failed to start")
        sys.exit(2)
    else:
        print("SUCCESS: All instances started")
        sys.exit(0)

if __name__ == '__main__':
    import os
    main()