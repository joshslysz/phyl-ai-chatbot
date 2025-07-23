#!/usr/bin/env python3
"""
Simple test script to debug MCP client integration.
"""

import os
import asyncio
import json
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

load_dotenv()

async def test_mcp_integration():
    """Test MCP client integration step by step."""
    
    database_uri = os.getenv('DATABASE_URI')
    if not database_uri:
        print("❌ DATABASE_URI not found")
        return False
    
    conn_string = f"{database_uri}?sslmode=require"
    
    # Simple MCP server command
    server_command = [
        "postgres-mcp",
        "--access-mode", "restricted", 
        "--transport", "stdio",
        conn_string
    ]
    
    print(f"Testing MCP integration...")
    print(f"Command: {' '.join(server_command[:3])} [DATABASE_URI]")
    print(f"Python version: {__import__('sys').version}")
    
    try:
        print("📡 Starting MCP client connection...")
        
        # Create a proper server configuration
        from mcp.client.stdio import StdioServerParameters
        server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:],
            env=None
        )
        
        async with stdio_client(server_params) as (read, write):
            print("✅ MCP stdio connection established")
            
            async with ClientSession(read, write) as session:
                print("✅ MCP client session created")
                
                # Wait for server initialization
                print("⏳ Waiting for server initialization...")
                await asyncio.sleep(2)
                
                # Initialize the session
                print("🔧 Initializing MCP session...")
                await session.initialize()
                
                # List available tools
                print("\n🔍 Listing available MCP tools...")
                tools = await session.list_tools()
                print(f"Available tools: {[tool.name for tool in tools.tools]}")
                
                # First try list_objects to understand the format
                print("\n🔍 Testing list_objects tool...")
                result = await session.call_tool("list_objects", {})
                
                print(f"List_objects result: {result.content[0].text if result.content else 'No content'}")
                
                # Try a simple query with execute_sql tool using different parameter name
                print("\n🔍 Testing execute_sql tool with 'sql' parameter...")
                result = await session.call_tool("execute_sql", {
                    "sql": "SELECT 1 as test"
                })
                
                print(f"Execute_sql result type: {type(result)}")
                print(f"Execute_sql result content: {result.content}")
                
                if result.content:
                    print(f"Result text: {result.content[0].text}")
                
                # Try the schedule table query
                print("\n🔍 Testing schedule table query...")
                result = await session.call_tool("execute_sql", {
                    "query": "SELECT * FROM schedule ORDER BY week"
                })
                
                print(f"Query result type: {type(result)}")
                print(f"Query result content: {result.content}")
                
                if result.content:
                    print(f"Result text: {result.content[0].text}")
                
                return True
                
    except Exception as e:
        print(f"❌ MCP integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_integration())
    if success:
        print("\n✅ MCP integration test successful!")
    else:
        print("\n❌ MCP integration test failed!")