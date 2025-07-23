#!/usr/bin/env python3

import asyncio
import os
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()

async def test_raw_output():
    """Test raw MCP output."""
    
    DATABASE_URI = os.getenv("DATABASE_URI")
    
    try:
        env = os.environ.copy()
        env['DATABASE_URI'] = DATABASE_URI
        
        server_params = StdioServerParameters(
            command="/home/joshslysz/projects/phyl-chatbot/backend/phyl-chatbot/bin/postgres-mcp",
            args=["--access-mode", "restricted", "--transport", "stdio"],
            env=env
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                
                await session.initialize()
                
                print("=== RAW LIST_OBJECTS OUTPUT ===")
                result = await session.call_tool("list_objects", {"schema_name": "public"})
                raw_text = result.content[0].text
                print(f"Type: {type(raw_text)}")
                print(f"Length: {len(raw_text)}")
                print(f"Content: '{raw_text}'")
                print(f"First 50 chars: '{raw_text[:50]}'")
                
                print("\n=== RAW MODULES SAMPLE ===")
                result = await session.call_tool("execute_sql", {"sql": "SELECT * FROM modules LIMIT 1"})
                raw_text = result.content[0].text
                print(f"Content: '{raw_text}'")
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_raw_output())