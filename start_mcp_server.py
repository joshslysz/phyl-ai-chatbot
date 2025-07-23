#!/usr/bin/env python3
"""
Helper script to start postgres-mcp server from Python 3.12 environment
while maintaining compatibility with FastAPI Python 3.10 environment.
"""

import os
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

def start_mcp_server():
    """Start postgres-mcp server using Python 3.12."""
    
    database_uri = os.getenv('DATABASE_URI')
    if not database_uri:
        print("❌ DATABASE_URI not found in .env file")
        return False
    
    # Add SSL requirement
    conn_string = f"{database_uri}?sslmode=require"
    
    # MCP server command
    cmd = [
        "/home/joshslysz/projects/phyl-chatbot/backend/phyl-chatbot/bin/postgres-mcp",
        "--access-mode", "restricted",
        "--transport", "stdio"
    ]
    
    print(f"Starting MCP server: {' '.join(cmd[:4])} [DATABASE_URI]")
    
    try:
        # Set up environment with DATABASE_URI
        env = os.environ.copy()
        env['DATABASE_URI'] = database_uri
        
        # Start the server
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return process
    except Exception as e:
        print(f"❌ Failed to start MCP server: {e}")
        return None

if __name__ == "__main__":
    server_process = start_mcp_server()
    if server_process:
        print("✅ MCP server started successfully")
        # Keep it running
        server_process.wait()
    else:
        print("❌ Failed to start MCP server")
        sys.exit(1)