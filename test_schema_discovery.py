#!/usr/bin/env python3

import asyncio
import os
import json
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()

async def discover_schema():
    """Discover the actual database schema."""
    
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
                
                print("=== TABLES ===")
                result = await session.call_tool("list_objects", {"schema_name": "public"})
                tables_data = json.loads(result.content[0].text)
                for table in tables_data:
                    print(f"- {table['name']}")
                
                print("\n=== TABLE STRUCTURES ===")
                for table in tables_data:
                    table_name = table['name']
                    print(f"\n--- {table_name.upper()} ---")
                    result = await session.call_tool("get_object_details", {
                        "object_name": table_name,
                        "schema_name": "public"
                    })
                    print(result.content[0].text)
                
                print("\n=== SAMPLE DATA FROM MODULES ===")
                result = await session.call_tool("execute_sql", {
                    "sql": "SELECT * FROM modules LIMIT 3"
                })
                print(result.content[0].text)
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(discover_schema())