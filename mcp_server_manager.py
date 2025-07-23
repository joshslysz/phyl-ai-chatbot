#!/usr/bin/env python3
"""
MCP Server Manager for postgres-mcp server.
Handles starting and managing the postgres-mcp server process.
"""

import os
import subprocess
import time
import signal
import sys
from dotenv import load_dotenv

load_dotenv()

class MCPServerManager:
    def __init__(self):
        self.process = None
        self.database_uri = os.getenv('DATABASE_URI')
        if not self.database_uri:
            raise RuntimeError("DATABASE_URI environment variable is required")
        
        # Add SSL requirement
        self.conn_string = f"{self.database_uri}?sslmode=require"
        
        # Command to start postgres-mcp server
        self.command = [
            "/home/joshslysz/projects/phyl-chatbot/backend/phyl-chatbot/bin/postgres-mcp",
            "--access-mode", "restricted",
            "--transport", "stdio"
        ]
    
    def start_server(self):
        """Start the postgres-mcp server."""
        if self.process and self.process.poll() is None:
            print("MCP server is already running")
            return True
        
        try:
            print(f"Starting MCP server...")
            print(f"Command: {' '.join(self.command)} [DATABASE_URI]")
            
            # Set up environment with DATABASE_URI
            env = os.environ.copy()
            env['DATABASE_URI'] = self.database_uri
            
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Check if it started successfully
            if self.process.poll() is None:
                print("✅ MCP server started successfully")
                return True
            else:
                stdout, stderr = self.process.communicate()
                print(f"❌ MCP server failed to start:")
                print(f"stdout: {stdout}")
                print(f"stderr: {stderr}")
                return False
        
        except Exception as e:
            print(f"❌ Failed to start MCP server: {e}")
            return False
    
    def stop_server(self):
        """Stop the postgres-mcp server."""
        if self.process and self.process.poll() is None:
            print("Stopping MCP server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Force killing MCP server...")
                self.process.kill()
            print("✅ MCP server stopped")
        else:
            print("MCP server is not running")
    
    def is_running(self):
        """Check if the MCP server is running."""
        return self.process and self.process.poll() is None
    
    def get_process(self):
        """Get the server process for stdio communication."""
        return self.process

def signal_handler(sig, frame):
    """Handle shutdown signals."""
    print("\nReceived shutdown signal...")
    if 'manager' in globals():
        manager.stop_server()
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start server manager
    manager = MCPServerManager()
    
    if manager.start_server():
        print("MCP server is running. Press Ctrl+C to stop.")
        try:
            while manager.is_running():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            manager.stop_server()
    else:
        print("Failed to start MCP server")
        sys.exit(1)