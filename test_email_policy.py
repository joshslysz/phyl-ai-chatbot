#!/usr/bin/env python3
import asyncio
import time
import os
import sys
sys.path.append('/home/joshslysz/projects/phyl-chatbot/backend')

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

from main import query_mcp_server, claude_client
import json

async def test_email_policy_direct():
    """Test email policy question with direct SQL approach."""
    
    question = "what is the email policy"
    print(f"🔍 Testing: {question}")
    print("=" * 60)
    
    start_time = time.time()
    
    try:
        # Step 1: Search for email policy directly
        logging.info("Executing targeted SQL for email policy")
        result = await query_mcp_server(
            sql_query="SELECT policy_category, policy_name, policy_description, details, specific_rules FROM policies WHERE policy_name ILIKE '%email%' OR policy_description ILIKE '%email%' OR details ILIKE '%email%';",
            use_tool="execute_sql"
        )
        
        if result.get("success") and result.get("data"):
            # Generate final response using Claude
            final_prompt = f"""Student Question: "{question}"
SQL Results: {json.dumps(result["data"])}

The student is asking about the course email policy. Use the provided data to give them a clear, helpful explanation of the email policy. Include specific details like response times and rules."""

            final_response = claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": final_prompt}]
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"⏱️  Response time: {duration:.2f} seconds")
            print("📝 Full response:")
            print("-" * 40)
            print(final_response.content[0].text)
            print("-" * 40)
            
            return final_response.content[0].text
        else:
            print(f"❌ No email policy data found: {result}")
            return "No email policy found"
            
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        print(f"❌ Error after {duration:.2f} seconds: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    asyncio.run(test_email_policy_direct())