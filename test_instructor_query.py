#!/usr/bin/env python3

import asyncio
import os
import json
from dotenv import load_dotenv
from main import claude_orchestrated_query

load_dotenv()

async def test_instructor_query():
    """Test the instructor query directly."""
    
    print("Testing 'who are the instructors' query...")
    print("=" * 50)
    
    try:
        # Test the orchestrated query function directly
        result = await claude_orchestrated_query("who are the instructors")
        print("Result:")
        print(result)
        print("=" * 50)
        print("SUCCESS: Query completed")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_instructor_query())