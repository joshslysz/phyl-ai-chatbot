#!/usr/bin/env python3
import asyncio
import time
import os
import sys
sys.path.append('/home/joshslysz/projects/phyl-chatbot/backend')

from dotenv import load_dotenv
load_dotenv()

# Mock the required imports for testing
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

from main import claude_orchestrated_query_optimized

async def test_performance():
    """Test the optimized MCP integration performance."""
    
    test_questions = [
        "What assignments are available?",
        "What are the course policies?", 
        "What modules are covered?"
    ]
    
    print("🚀 Testing Optimized MCP Integration Performance")
    print("=" * 60)
    
    total_time = 0
    for i, question in enumerate(test_questions, 1):
        print(f"\n📋 Test {i}: {question}")
        print("-" * 40)
        
        start_time = time.time()
        try:
            result = await claude_orchestrated_query_optimized(question)
            end_time = time.time()
            duration = end_time - start_time
            total_time += duration
            
            print(f"⏱️  Response time: {duration:.2f} seconds")
            print(f"📝 Result preview: {result[:150]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            end_time = time.time()
            duration = end_time - start_time
            total_time += duration
            print(f"⏱️  Failed after: {duration:.2f} seconds")
    
    print("\n" + "=" * 60)
    print(f"📊 PERFORMANCE SUMMARY")
    print(f"Total time for {len(test_questions)} questions: {total_time:.2f} seconds")
    print(f"Average time per question: {total_time/len(test_questions):.2f} seconds")
    print(f"Target was 5 seconds per question: {'✅ ACHIEVED' if total_time/len(test_questions) <= 5 else '❌ NEEDS MORE OPTIMIZATION'}")

if __name__ == "__main__":
    asyncio.run(test_performance())