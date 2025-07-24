#!/usr/bin/env python3

import asyncio
import os
import ast
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()

async def find_instructors():
    """Find instructor information in the database."""
    
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
                
                print("=== CHECKING ALL TABLES FOR INSTRUCTOR INFO ===")
                
                # Check each table for any instructor-related columns
                tables = ['assignments', 'modules', 'policies', 'course_info']
                
                for table in tables:
                    print(f"\n--- {table.upper()} TABLE ---")
                    
                    # Get table structure first
                    result = await session.call_tool("get_object_details", {
                        "object_name": table,
                        "schema_name": "public"
                    })
                    print(f"Structure: {result.content[0].text}")
                    
                    # Get sample data
                    result = await session.call_tool("execute_sql", {
                        "sql": f"SELECT * FROM {table} LIMIT 2"
                    })
                    raw_text = result.content[0].text
                    print(f"Sample data: {raw_text}")
                    
                    # Try to find any columns that might contain instructor info
                    try:
                        data_list = ast.literal_eval(raw_text)
                        if data_list:
                            sample_row = data_list[0]
                            instructor_columns = [col for col in sample_row.keys() if 'instructor' in col.lower() or 'teacher' in col.lower() or 'prof' in col.lower()]
                            if instructor_columns:
                                print(f"Found potential instructor columns: {instructor_columns}")
                    except:
                        pass
                    
                    print("-" * 40)
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(find_instructors())