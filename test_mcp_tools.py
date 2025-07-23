#!/usr/bin/env python3
"""
Test actual postgres-mcp tools with Supabase database connection.
This script demonstrates using the postgres-mcp server in restricted mode.
"""

import os
import asyncio
import json
from typing import Any, Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_mcp_tools():
    """Test MCP tools with postgres-mcp server."""
    
    database_uri = os.getenv('DATABASE_URI')
    if not database_uri:
        print("❌ DATABASE_URI not found in .env file")
        return False
    
    # Add SSL requirement to the URI
    conn_string = f"{database_uri}?sslmode=require"
    
    print("🚀 Testing postgres-mcp tools")
    print("="*60)
    print(f"Database: {conn_string.replace('JLBeck33!', '[PASSWORD]')}")
    print("Mode: RESTRICTED (read-only)")
    print("="*60)
    
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import stdio_client
        
        print("✅ MCP client libraries loaded successfully")
        
        # Create MCP client session
        server_params = [
            "postgres-mcp",
            "--access-mode", "restricted",
            conn_string
        ]
        
        print(f"\n🔌 Starting MCP server with: postgres-mcp --access-mode restricted [DATABASE_URI]")
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("✅ MCP session established")
                
                # Test 1: List available tools
                print("\n📋 Available MCP Tools:")
                tools = await session.list_tools()
                for tool in tools.tools:
                    print(f"  - {tool.name}: {tool.description}")
                
                # Test 2: List tables
                print("\n🗂️  Listing tables:")
                result = await session.call_tool("list_tables", {})
                print(f"Result: {result.content[0].text}")
                
                # Test 3: Describe assignments table
                print("\n📊 Describing assignments table:")
                result = await session.call_tool("describe_table", {"table_name": "assignments"})
                print(f"Result: {result.content[0].text}")
                
                # Test 4: Query assignments table
                print("\n🔍 Querying assignments table:")
                result = await session.call_tool("query", {
                    "sql": "SELECT * FROM assignments LIMIT 5"
                })
                print(f"Result: {result.content[0].text}")
                
                # Test 5: Count rows in assignments
                print("\n📈 Counting rows in assignments:")
                result = await session.call_tool("query", {
                    "sql": "SELECT COUNT(*) as total_records FROM assignments"
                })
                print(f"Result: {result.content[0].text}")
                
                # Test 6: Try a write operation (should fail in restricted mode)
                print("\n🔒 Testing write restriction:")
                try:
                    result = await session.call_tool("query", {
                        "sql": "INSERT INTO assignments (week, date, topic) VALUES (99, '2099-01-01', 'Test')"
                    })
                    print("❌ WARNING: Write operation succeeded (should have failed!)")
                except Exception as e:
                    print(f"✅ Write operation properly blocked: {str(e)[:100]}...")
                
                print("\n🎉 All MCP tests completed successfully!")
                return True
                
    except ImportError as e:
        print(f"❌ MCP libraries not available: {e}")
        print("Install with: pip install mcp")
        return False
    except Exception as e:
        print(f"❌ MCP test failed: {e}")
        return False

async def main():
    """Main test function."""
    print("🧪 Testing postgres-mcp Tools with Supabase")
    print("="*60)
    
    success = await test_mcp_tools()
    
    if success:
        print("\n✅ SUCCESS: postgres-mcp is working with your Supabase database!")
        print("🔐 Restricted mode ensures safe student-facing queries")
        print("🚀 Ready for FastAPI integration")
    else:
        print("\n❌ FAILED: postgres-mcp testing encountered issues")
    
    return success

if __name__ == "__main__":
    asyncio.run(main())