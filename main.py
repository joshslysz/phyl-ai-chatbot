import os
import asyncio
import json
import ast
import atexit
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp_server_manager import MCPServerManager
import anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

# MCP server configuration
DATABASE_URI = os.getenv("DATABASE_URI")
if not DATABASE_URI:
    raise RuntimeError("DATABASE_URI environment variable is required")

# MCP server connection string
MCP_DATABASE_URI = f"{DATABASE_URI}?sslmode=require"

# Claude API configuration
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
if not CLAUDE_API_KEY:
    raise RuntimeError("CLAUDE_API_KEY environment variable is required")

# Initialize Claude client
claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Global MCP server manager instance
mcp_manager = None

async def parse_mcp_result(result_text: str, tool_name: str = None) -> Dict[str, Any]:
    """
    Robustly parse MCP server results that may be in JSON or Python literal notation.
    
    Args:
        result_text: Raw text from MCP server
        tool_name: Name of the MCP tool for logging context
        
    Returns:
        Parsed data structure or fallback dict with raw_text
    """
    if not result_text.strip():
        logging.warning(f"MCP tool {tool_name}: Empty result")
        return {"raw_text": result_text}
    
    # First, try standard JSON parsing (proper JSON with double quotes)
    try:
        parsed_result = json.loads(result_text)
        logging.debug(f"MCP tool {tool_name}: Successfully parsed as JSON")
        return parsed_result
    except json.JSONDecodeError as json_error:
        logging.debug(f"MCP tool {tool_name}: JSON parsing failed: {json_error}")
    
    # Second, try Python literal evaluation (handles single quotes, True/False/None)
    try:
        parsed_result = ast.literal_eval(result_text)
        logging.info(f"MCP tool {tool_name}: Successfully parsed as Python literal (single quotes converted)")
        return parsed_result
    except (ValueError, SyntaxError) as ast_error:
        logging.debug(f"MCP tool {tool_name}: Python literal parsing failed: {ast_error}")
    
    # Third, try converting single quotes to double quotes and parse as JSON
    try:
        # Simple quote conversion (be careful with this approach)
        json_text = result_text.replace("'", '"')
        # Handle Python boolean/null values
        json_text = json_text.replace('True', 'true').replace('False', 'false').replace('None', 'null')
        parsed_result = json.loads(json_text)
        logging.info(f"MCP tool {tool_name}: Successfully parsed after quote conversion")
        return parsed_result
    except json.JSONDecodeError as converted_error:
        logging.debug(f"MCP tool {tool_name}: Quote conversion parsing failed: {converted_error}")
    
    # Final fallback: Return as raw text with warning
    logging.warning(f"MCP tool {tool_name}: All parsing methods failed, returning raw text. Content: {result_text[:200]}...")
    return {"raw_text": result_text, "parsing_error": "Could not parse as JSON or Python literal"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global mcp_manager
    mcp_manager = MCPServerManager()
    
    print("Starting MCP server...")
    if mcp_manager.start_server():
        print("✅ MCP server started successfully")
    else:
        print("❌ Failed to start MCP server")
        raise RuntimeError("Could not start MCP server")
    
    # Register cleanup function
    def cleanup():
        if mcp_manager:
            mcp_manager.stop_server()
    
    atexit.register(cleanup)
    
    yield
    
    # Shutdown
    print("Shutting down MCP server...")
    if mcp_manager:
        mcp_manager.stop_server()

app = FastAPI(lifespan=lifespan)

# Pydantic models
class QuestionRequest(BaseModel):
    question: str

class AnswerResponse(BaseModel):
    answer: str
    sources: List[str] = []
    course_data: List[Dict[str, Any]] = []

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def root():
    return {"message": "Phyl Chatbot API is running!"}

@app.get("/health")
async def health_check():
    global mcp_manager
    mcp_status = "running" if mcp_manager and mcp_manager.is_running() else "stopped"
    return {
        "status": "healthy",
        "mcp_server": mcp_status
    }

@app.get("/config")
async def get_config():
    return {
        "openai_key_loaded": bool(os.getenv("OPENAI_API_KEY")),
        "claude_key_loaded": bool(os.getenv("CLAUDE_API_KEY")),
        "database_uri_loaded": bool(os.getenv("DATABASE_URI")),
        "mcp_integration": "enabled"
    }

async def query_mcp_server(sql_query: str = None, use_tool: str = "execute_sql", schema_name: str = "public", object_name: str = None) -> Dict[str, Any]:
    """Execute queries using fresh MCP connections."""
    
    # Log the MCP tool execution
    tool_input = {
        "use_tool": use_tool,
        "sql_query": sql_query,
        "schema_name": schema_name,
        "object_name": object_name
    }
    logging.info(f"Executing MCP tool: {use_tool} with input: {json.dumps({k: v for k, v in tool_input.items() if v is not None})}")
    
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
                # Initialize the session
                await session.initialize()
                
                if use_tool == "list_objects":
                    result = await session.call_tool("list_objects", {"schema_name": schema_name})
                elif use_tool == "get_object_details" and object_name:
                    result = await session.call_tool("get_object_details", {
                        "object_name": object_name,
                        "schema_name": schema_name
                    })
                elif use_tool == "execute_sql" and sql_query:
                    # Log SQL execution specifically
                    logging.info(f"Generated SQL: {sql_query}")
                    result = await session.call_tool("execute_sql", {"sql": sql_query})
                else:
                    raise Exception("Invalid tool or missing required parameters")
                
                # Extract result content
                if result.content and len(result.content) > 0:
                    result_text = result.content[0].text.strip()
                    parsed_result = await parse_mcp_result(result_text, use_tool)
                    
                    # Enhanced logging for SQL results
                    if use_tool == "execute_sql":
                        if "raw_text" in parsed_result:
                            logging.error(f"SQL parsing failed - Claude will receive raw text: {parsed_result.get('raw_text', '')[:200]}")
                        elif isinstance(parsed_result, list):
                            logging.info(f"SQL returned {len(parsed_result)} rows - Claude will receive structured data")
                            if parsed_result:
                                logging.info(f"Sample result: {json.dumps(parsed_result[0])[:200]}")
                            else:
                                logging.warning("SQL query returned no results - check if search terms match data")
                        else:
                            logging.info(f"SQL result (non-list): {json.dumps(parsed_result)[:200]}")

                    # Log the MCP tool result with parsing status
                    if "raw_text" in parsed_result:
                        logging.warning(f"MCP tool {use_tool} - PARSING FAILED - Claude receives: {json.dumps(parsed_result)[:500]}")
                    else:
                        logging.info(f"MCP tool {use_tool} - PARSING SUCCESS - Claude receives: {json.dumps(parsed_result)[:500]}")
                    
                    return {"success": True, "data": parsed_result}
                else:
                    logging.warning(f"MCP tool {use_tool} returned no content")
                    return {"success": False, "data": {}}
    
    except Exception as e:
        logging.error(f"Error executing MCP tool {use_tool}: {str(e)}")
        return {"success": False, "data": None, "raw": f"MCP server error: {str(e)}"}

async def generate_intelligent_sql_query(question: str, schema_info: str) -> str:
    """Use Claude to generate an intelligent SQL query based on the user's question and database schema."""
    
    prompt = f"""You are a SQL expert. Based on the following database schema and user question, generate an appropriate SQL query.

Database Schema:
{schema_info}

User Question: "{question}"

Generate a SQL query that would best answer this question. Consider:
1. Which tables are most relevant to the question
2. What columns should be selected
3. Appropriate WHERE clauses if needed
4. Proper ORDER BY clauses based on the actual column names in the schema
5. JOINs if multiple tables are needed

Return ONLY the SQL query, nothing else. If multiple queries are needed, separate them with semicolons."""
    
    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text.strip()
    except Exception as e:
        # Fallback to a safe general query if Claude fails
        return "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"

async def claude_orchestrated_query_optimized(question: str) -> str:
    """Optimized Claude MCP workflow: Fresh connections with smart discovery."""
    
    logging.info(f"Processing question: {question}")
    
    try:
        # Use fresh connections but optimize the workflow
        result = await execute_fresh_connection_workflow(question)
        return result
        
    except Exception as e:
        logging.error(f"Error in optimized query: {str(e)}")
        return f"I encountered an error while processing your question: {str(e)}"

async def execute_fresh_connection_workflow(question: str) -> str:
    """Execute optimized workflow using fresh connections for reliability."""
    
    logging.info("Starting fresh-connection optimized workflow")
    
    try:
        # Step 1: Discover tables (1 connection)
        logging.info("Step 1: Discovering tables")
        tables_result = await query_mcp_server(use_tool="list_objects", schema_name="public")
        
        if not tables_result.get("success") or not tables_result.get("data"):
            return "I couldn't access the database tables."
        
        # Extract table names
        tables_data = tables_result["data"]
        table_names = []
        if isinstance(tables_data, list):
            table_names = [table.get("name", "") for table in tables_data if table.get("type") in ["table", "BASE TABLE"]]
        
        logging.info(f"Discovered tables: {table_names}")
        
        # Step 2: Generate smart SQL without needing schemas (avoid extra connections)
        sql_query = generate_smart_sql_no_schema(question, table_names)
        logging.info(f"Generated smart SQL: {sql_query}")
        
        # Step 3: Execute SQL (1 connection)
        sql_result = await query_mcp_server(sql_query=sql_query, use_tool="execute_sql")
        
        if sql_result.get("success") and sql_result.get("data"):
            # Step 4: Generate final response using Claude
            final_prompt = f"""Student Question: "{question}"
Available Tables: {', '.join(table_names)}
SQL Results: {json.dumps(sql_result["data"])}

Provide a clear, conversational answer using the data. Don't mention SQL or technical details."""

            final_response = claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": final_prompt}]
            )
            
            logging.info("Fresh-connection workflow completed successfully")
            return final_response.content[0].text
        else:
            return "I couldn't find any relevant information for your question."
    
    except Exception as e:
        logging.error(f"Error in fresh-connection workflow: {e}")
        return f"I encountered an error while processing your question: {str(e)}"

def generate_smart_sql_no_schema(question: str, table_names: List[str]) -> str:
    """Generate optimized SQL without needing schema discovery."""
    
    question_lower = question.lower()
    
    # Smart keyword-based routing
    if "assignments" in table_names and any(word in question_lower for word in ["assignment", "quiz", "test", "exam", "due", "homework"]):
        return "SELECT * FROM assignments ORDER BY due_date, week;"
    
    elif "modules" in table_names and any(word in question_lower for word in ["module", "topic", "cover", "subject", "unit"]):
        return "SELECT * FROM modules ORDER BY block_code, start_week;"
    
    elif "policies" in table_names and any(word in question_lower for word in ["policy", "rule", "grade", "attendance", "late", "extension", "email"]):
        # Enhanced policy search with specific term targeting
        search_terms = [word for word in question_lower.split() if len(word) > 3 and word not in ["what", "what's", "policy", "policies"]]
        
        # Look for specific policy keywords
        if "email" in question_lower:
            return "SELECT policy_category, policy_name, policy_description, details, specific_rules FROM policies WHERE policy_name ILIKE '%email%' OR policy_description ILIKE '%email%' OR details ILIKE '%email%' OR specific_rules ILIKE '%email%' ORDER BY policy_category, policy_name;"
        elif search_terms:
            term = search_terms[0]
            return f"SELECT policy_category, policy_name, policy_description, details, specific_rules FROM policies WHERE policy_name ILIKE '%{term}%' OR policy_description ILIKE '%{term}%' OR details ILIKE '%{term}%' OR specific_rules ILIKE '%{term}%' ORDER BY policy_category, policy_name;"
        else:
            return "SELECT policy_category, policy_name, policy_description, details, specific_rules FROM policies ORDER BY policy_category, policy_name;"
    
    elif "course_info" in table_names and any(word in question_lower for word in ["instructor", "teacher", "professor", "contact", "email", "office", "hours", "textbook", "book", "mastering", "cost", "price", "buy", "purchase", "class", "schedule", "time", "when", "where", "location", "room", "technology", "brightspace", "tophat", "collaborate", "support", "tutorial", "ta", "teaching", "assistant", "help", "course", "syllabus", "hybrid", "online", "format"]):
        return "SELECT * FROM course_info ORDER BY info_category, info_type;"
    
    else:
        # General search across all tables
        search_terms = [word for word in question_lower.split() if len(word) > 3]
        if search_terms and table_names:
            term = search_terms[0]
            union_queries = []
            
            for table_name in table_names:
                # Use common text column names
                if table_name == "assignments":
                    union_queries.append(f"SELECT 'assignment' as source, assignment_name as name, description as content FROM assignments WHERE assignment_name ILIKE '%{term}%' OR description ILIKE '%{term}%'")
                elif table_name == "modules":
                    union_queries.append(f"SELECT 'module' as source, module_name as name, module_description as content FROM modules WHERE module_name ILIKE '%{term}%' OR module_description ILIKE '%{term}%'")
                elif table_name == "policies":
                    union_queries.append(f"SELECT 'policy' as source, policy_name as name, policy_description as content FROM policies WHERE policy_name ILIKE '%{term}%' OR policy_description ILIKE '%{term}%'")
                elif table_name == "course_info":
                    union_queries.append(f"SELECT 'course_info' as source, title as name, details as content FROM course_info WHERE title ILIKE '%{term}%' OR details ILIKE '%{term}%' OR contact_info ILIKE '%{term}%' OR additional_notes ILIKE '%{term}%'")
            
            if union_queries:
                return " UNION ALL ".join(union_queries) + ";"
        
        # Fallback: return data from first available table
        if table_names:
            return f"SELECT * FROM {table_names[0]} LIMIT 10;"
        else:
            return "SELECT 1;"

# Removed broken single-connection implementation - using fresh connections for reliability

# Removed legacy functions - using optimized fresh connection approach

# Removed unused persistent connection code - using fresh connections for reliability

# Clean implementation with fresh connections for reliability

# Main entry point uses optimized fresh connection approach
async def claude_orchestrated_query(question: str) -> str:
    """Main Claude MCP workflow - uses optimized fresh connections."""
    return await claude_orchestrated_query_optimized(question)


async def claude_intelligent_query(question: str) -> str:
    """Claude orchestrates the entire workflow using fresh connections: discover schema → generate SQL → execute → format response."""
    
    # Create a comprehensive prompt for Claude to handle the entire workflow
    prompt = f"""You are a database assistant with access to MCP tools for a Supabase PostgreSQL database.

Student Question: "{question}"

Your database has these main tables: assignments, modules, policies, course_info

Available MCP tools:
1. mcp_list_objects(schema_name="public") - Lists all tables in the schema
2. mcp_get_object_details(object_name="table_name") - Gets column details for a table  
3. mcp_execute_sql(sql="SELECT ...") - Executes SQL queries (read-only)

CRITICAL: You MUST complete ALL steps of this workflow. Do not stop until you have executed a SQL query and provided a complete answer.

CRITICAL: Make ALL tool calls in your FIRST response. Do not wait for tool results to make the next call.

For email policy questions, you must immediately call:
1. mcp_list_objects(schema_name="public")
2. mcp_get_object_details(object_name="policies") 
3. mcp_execute_sql(sql="SELECT * FROM policies WHERE policy_name ILIKE '%email%' OR policy_description ILIKE '%email%' OR details ILIKE '%email%'")

IMPORTANT: Make all 3 tool calls RIGHT NOW in this response. Do not explain what you will do - just execute all the tools immediately."""

    try:
        # Create a conversation with Claude that can use MCP tools
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ],
            tools=[
                {
                    "name": "mcp_list_objects",
                    "description": "List database objects in a schema",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "schema_name": {"type": "string", "description": "Schema name (use 'public')"}
                        },
                        "required": ["schema_name"]
                    }
                },
                {
                    "name": "mcp_get_object_details", 
                    "description": "Get detailed information about a database object",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the database object"}
                        },
                        "required": ["object_name"]
                    }
                },
                {
                    "name": "mcp_execute_sql",
                    "description": "Execute a SQL query",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "SQL query to execute"}
                        },
                        "required": ["sql"]
                    }
                }
            ]
        )
        
        # Handle Claude's response and tool calls
        return await process_claude_tool_response(response, question)
        
    except Exception as e:
        return f"I encountered an error while processing your question: {str(e)}"

async def process_claude_tool_response(response, original_question: str) -> str:
    """Process Claude's response and handle any MCP tool calls using fresh connections."""
    
    logging.info(f"Processing Claude response with stop_reason: {response.stop_reason}")
    logging.info(f"Response content blocks: {len(response.content)}")
    
    # If Claude wants to use tools, handle them
    if response.stop_reason == "tool_use":
        logging.info("Claude wants to use tools - processing tool calls")
        tool_results = []
        
        for i, content_block in enumerate(response.content):
            logging.info(f"Content block {i}: type={content_block.type}")
            if content_block.type == "tool_use":
                tool_name = content_block.name
                tool_input = content_block.input
                logging.info(f"Executing tool: {tool_name} with input: {tool_input}")
                
                # Execute the MCP tool using fresh connections (like current system)
                if tool_name == "mcp_list_objects":
                    result = await query_mcp_server(use_tool="list_objects", schema_name=tool_input["schema_name"])
                elif tool_name == "mcp_get_object_details":
                    result = await query_mcp_server(use_tool="get_object_details", object_name=tool_input["object_name"])
                elif tool_name == "mcp_execute_sql":
                    result = await query_mcp_server(sql_query=tool_input["sql"], use_tool="execute_sql")
                else:
                    result = {"success": False, "raw": f"Unknown tool: {tool_name}"}
                
                logging.info(f"Tool {tool_name} executed, result: {str(result)[:200]}...")
                
                # Add tool result
                tool_results.append({
                    "role": "user", 
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": result.get("raw", str(result))
                    }]
                })
        
        logging.info(f"Processed {len(tool_results)} tool calls, continuing conversation")
        
        # Continue conversation with tool results - be extremely direct
        messages = [
            {"role": "user", "content": f"EXECUTE STEP 2 NOW: Call mcp_get_object_details(object_name=\"policies\") immediately. Do not explain, just make the tool call."},
            {"role": "assistant", "content": response.content}
        ] + tool_results
        
        logging.info(f"Sending continuation message to Claude with {len(messages)} total messages")
        
        # Get final response from Claude
        final_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages
        )
        
        logging.info(f"Final response stop_reason: {final_response.stop_reason}")
        logging.info(f"Final response content blocks: {len(final_response.content)}")
        
        if len(final_response.content) == 0:
            logging.error("Final response has no content blocks!")
            return "I encountered an issue processing the response - no content returned."
        
        logging.info(f"Final response content: {str(final_response.content[0])[:200]}...")
        
        # Handle potential additional tool calls in final response
        if final_response.stop_reason == "tool_use":
            logging.info("Final response has tool_use, recursing...")
            return await process_claude_tool_response(final_response, original_question)
        else:
            logging.info("Final response is text, returning...")
            return final_response.content[0].text
    
    else:
        logging.info("Claude provided direct response (no tools)")
        return response.content[0].text

async def generate_claude_response(question: str, course_data: List[Dict[str, Any]], schema_info: str = None, data_sources: List[str] = None) -> str:
    """Generate a conversational response using Claude 3.5 Sonnet based on the user's question and course data."""
    
    # Format course data for Claude
    data_context = ""
    if course_data:
        # Determine data source context based on what tables were queried
        if data_sources and len(data_sources) == 1:
            source_name = data_sources[0].replace('_', ' ').title()
            data_context = f"Course {source_name} Data:\n"
        else:
            data_context = "Course Data:\n"
            
        for item in course_data:
            if isinstance(item, dict):
                if 'error' in item:
                    data_context += f"Error: {item['error']}\n"
                elif 'mcp_result' in item:
                    data_context += f"Raw data: {item['mcp_result']}\n"
                else:
                    # Format structured data nicely
                    for key, value in item.items():
                        data_context += f"{key}: {value}\n"
                    data_context += "---\n"
    
    # Add schema information if available
    if schema_info:
        data_context += f"\nDatabase Schema: {schema_info}\n"
    
    # Construct prompt for Claude
    prompt = f"""You are an educational chatbot assistant for a course management system. 
A student has asked: "{question}"

Here is the relevant course data from the database:
{data_context}

Please provide a helpful, conversational response that:
1. Directly answers the student's question using the provided data
2. Is friendly and educational in tone
3. Explains any relevant course information clearly
4. If the data shows errors or is incomplete, acknowledge this and suggest what the student might do

Keep your response concise but informative, as if you're talking to a student."""

    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        return f"I'm having trouble processing your question right now. Here's what I found in the course data: {data_context[:500]}..."

@app.post("/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest):
    # Basic error handling for empty questions
    if not request.question or request.question.strip() == "":
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        # Use hybrid approach: hardcoded routing + intelligent SQL generation
        answer = await claude_orchestrated_query(request.question)
        
        return AnswerResponse(
            answer=answer,
            sources=["Claude + Postgres MCP integration"],
            course_data=[]
        )
    
    except Exception as e:
        # Handle errors
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing question: {str(e)}"
        )