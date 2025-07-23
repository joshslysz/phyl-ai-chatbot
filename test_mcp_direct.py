#!/usr/bin/env python3

import asyncio
import os
import json
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()

async def test_mcp_direct():
    """Test MCP server directly without using the manager."""
    
    DATABASE_URI = os.getenv("DATABASE_URI")
    if not DATABASE_URI:
        print("ERROR: DATABASE_URI not found")
        return
    
    print(f"Testing MCP server directly...")
    print(f"DATABASE_URI: {DATABASE_URI[:20]}...")
    print("=" * 50)
    
    try:
        # Set up environment
        env = os.environ.copy()
        env['DATABASE_URI'] = DATABASE_URI
        
        server_params = StdioServerParameters(
            command="/home/joshslysz/projects/phyl-chatbot/backend/phyl-chatbot/bin/postgres-mcp",
            args=["--access-mode", "restricted", "--transport", "stdio"],
            env=env
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                
                print("Initializing session...")
                await session.initialize()
                print("✅ Session initialized")
                
                print("Calling list_objects...")
                result = await session.call_tool("list_objects", {"schema_name": "public"})
                print(f"✅ list_objects result: {result.content[0].text}")
                
                print("Calling get_object_details for 'modules' table...")
                result = await session.call_tool("get_object_details", {"object_name": "modules"})
                print(f"✅ get_object_details result: {result.content[0].text}")
                
                print("Executing SQL query...")
                result = await session.call_tool("execute_sql", {
                    "sql": "SELECT instructor_name FROM modules LIMIT 5"
                })
                print(f"✅ execute_sql result: {result.content[0].text}")
        
        print("=" * 50)
        print("SUCCESS: All MCP operations completed")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_direct())