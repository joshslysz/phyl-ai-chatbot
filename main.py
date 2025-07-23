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

async def claude_orchestrated_query(question: str) -> str:
    """Claude orchestrates the entire MCP workflow through explicit step-by-step execution."""
    
    logging.info(f"Processing question: {question}")
    
    # Step 1: Get table list
    step1_prompt = f"""You are a database assistant. The student asked: "{question}"

STEP 1: Discover available tables using the mcp_list_objects tool.

You MUST call mcp_list_objects with schema_name="public" to see what tables are available. Do this now."""

    # Step 2: Get column details for relevant tables
    step2_prompt_template = """STEP 2: Now examine the column structure of relevant tables.

Based on the question "{question}" and these available tables: {tables}

You MUST call mcp_get_object_details for each table that might contain relevant data. Focus on tables likely to contain information about: {question}

Call mcp_get_object_details for each relevant table NOW."""

    # Step 3: Generate and execute SQL
    step3_prompt_template = """STEP 3: Generate and execute SQL query.

Student Question: "{question}"
Available Tables: {tables}
Column Details: {columns}

You MUST:
1. Generate a SQL query that searches ALL relevant text columns using ILIKE and OR conditions
2. Use this pattern: WHERE col1 ILIKE '%term%' OR col2 ILIKE '%term%' OR col3 ILIKE '%term%'
3. Extract key terms from the question and search across descriptive text columns
4. Call mcp_execute_sql with your generated query

Generate the SQL and execute it NOW using mcp_execute_sql."""

    # Step 4: Format final response
    step4_prompt_template = """STEP 4: Provide the final answer to the student.

Student Question: "{question}"
SQL Results: {results}

Provide a clear, conversational answer to the student's question using the data. Do NOT mention SQL, databases, or technical details - just give them a helpful response."""

    try:
        # Execute Step 1: List tables
        logging.info("STEP 1: Requesting table list from Claude")
        messages = [{"role": "user", "content": step1_prompt}]
        
        step1_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages,
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
        
        # Process step 1 tool calls and build conversation
        messages.append({"role": "assistant", "content": step1_response.content})
        tables_data = ""
        
        if step1_response.stop_reason == "tool_use":
            logging.info("STEP 1: Claude called list_objects - executing MCP tool")
            for content_block in step1_response.content:
                if content_block.type == "tool_use" and content_block.name == "mcp_list_objects":
                    result = await query_mcp_server(use_tool="list_objects", schema_name=content_block.input["schema_name"])
                    tables_data = json.dumps(result["data"])
                    logging.info(f"STEP 1: Found tables: {tables_data[:200]}...")
                    messages.append({
                        "role": "tool",
                        "tool_use_id": content_block.id,
                        "content": tables_data
                    })
        else:
            logging.warning("STEP 1: Claude did not call list_objects tool!")
        
        # Execute Step 2: Get column details
        logging.info("STEP 2: Requesting column details from Claude")
        step2_prompt = step2_prompt_template.format(question=question, tables=tables_data)
        messages.append({"role": "user", "content": step2_prompt})
        
        step2_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=messages,
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
        
        # Process step 2 tool calls
        messages.append({"role": "assistant", "content": step2_response.content})
        columns_data = ""
        
        if step2_response.stop_reason == "tool_use":
            logging.info("STEP 2: Claude called get_object_details - executing MCP tools")
            for content_block in step2_response.content:
                if content_block.type == "tool_use" and content_block.name == "mcp_get_object_details":
                    table_name = content_block.input["object_name"]
                    result = await query_mcp_server(use_tool="get_object_details", object_name=table_name)
                    columns_data += f"\nTable {table_name}: {json.dumps(result['data'])}"
                    logging.info(f"STEP 2: Got schema for table '{table_name}': {json.dumps(result['data'])[:200]}...")
                    messages.append({
                        "role": "tool",
                        "tool_use_id": content_block.id,
                        "content": json.dumps(result["data"])
                    })
        else:
            logging.warning("STEP 2: Claude did not call get_object_details tool!")
        
        # Execute Step 3: Generate and execute SQL
        logging.info("STEP 3: Requesting SQL generation and execution from Claude")
        step3_prompt = step3_prompt_template.format(
            question=question, 
            tables=tables_data, 
            columns=columns_data
        )
        messages.append({"role": "user", "content": step3_prompt})
        
        step3_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=messages,
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
        
        # Process step 3 tool calls
        messages.append({"role": "assistant", "content": step3_response.content})
        sql_results = ""
        
        if step3_response.stop_reason == "tool_use":
            logging.info("STEP 3: Claude called execute_sql - executing MCP tool")
            for content_block in step3_response.content:
                if content_block.type == "tool_use" and content_block.name == "mcp_execute_sql":
                    sql_query = content_block.input["sql"]
                    logging.info(f"STEP 3: Claude generated SQL: {sql_query}")
                    result = await query_mcp_server(sql_query=sql_query, use_tool="execute_sql")
                    sql_results = json.dumps(result["data"])
                    logging.info(f"STEP 3: SQL returned {len(result.get('data', []))} results")
                    messages.append({
                        "role": "tool",
                        "tool_use_id": content_block.id,
                        "content": sql_results
                    })
        else:
            logging.warning("STEP 3: Claude did not call execute_sql tool!")
        
        # Execute Step 4: Generate final response
        logging.info("STEP 4: Generating final conversational response")
        step4_prompt = step4_prompt_template.format(
            question=question,
            results=sql_results
        )
        
        final_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": step4_prompt}]
        )
        
        logging.info("STEP 4: Workflow completed successfully")
        
        return final_response.content[0].text
        
    except Exception as e:
        logging.error(f"Error in claude_orchestrated_query: {str(e)}")
        return f"I encountered an error while processing your question: {str(e)}"


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
        # Use Claude to orchestrate the entire MCP workflow
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