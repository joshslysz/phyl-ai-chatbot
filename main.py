import os
import asyncio
import json
import atexit
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
                    result = await session.call_tool("execute_sql", {"sql": sql_query})
                else:
                    raise Exception("Invalid tool or missing required parameters")
                
                # Extract result content
                if result.content and len(result.content) > 0:
                    result_text = result.content[0].text
                    
                    # Handle Python literal eval for single-quoted JSON
                    try:
                        import ast
                        parsed_result = ast.literal_eval(result_text)
                        return {"success": True, "data": parsed_result, "raw": result_text}
                    except (ValueError, SyntaxError):
                        # Try standard JSON parsing
                        try:
                            parsed_result = json.loads(result_text)
                            return {"success": True, "data": parsed_result, "raw": result_text}
                        except json.JSONDecodeError:
                            return {"success": True, "data": None, "raw": result_text}
                else:
                    return {"success": False, "data": None, "raw": "No results returned"}
    
    except Exception as e:
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
    """Claude orchestrates the entire MCP workflow: discover schema → generate SQL → execute → format response."""
    
    # Create a comprehensive prompt for Claude to handle the entire workflow
    prompt = f"""You are a database assistant with access to MCP tools for a Supabase PostgreSQL database.

Student Question: "{question}"

Your database has 3 main tables: assignments, modules, policies

Available MCP tools:
1. list_objects(schema_name="public") - Lists all tables in the schema
2. get_object_details(object_name="table_name") - Gets column details for a table  
3. execute_sql(sql="SELECT ...") - Executes SQL queries (read-only)

WORKFLOW:
1. First, discover the database schema using MCP tools
2. Analyze which table(s) are relevant to the question
3. Generate appropriate SQL query
4. Execute the SQL using MCP
5. Format the results into a natural language response

Start by exploring the database schema to understand the available data."""

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
        return await process_claude_response(response, question)
        
    except Exception as e:
        return f"I encountered an error while processing your question: {str(e)}"

async def process_claude_response(response, original_question: str) -> str:
    """Process Claude's response and handle any MCP tool calls."""
    
    # If Claude wants to use tools, handle them
    if response.stop_reason == "tool_use":
        tool_results = []
        
        for content_block in response.content:
            if content_block.type == "tool_use":
                tool_name = content_block.name
                tool_input = content_block.input
                
                # Execute the MCP tool
                if tool_name == "mcp_list_objects":
                    result = await query_mcp_server(use_tool="list_objects", schema_name=tool_input["schema_name"])
                elif tool_name == "mcp_get_object_details":
                    result = await query_mcp_server(use_tool="get_object_details", object_name=tool_input["object_name"])
                elif tool_name == "mcp_execute_sql":
                    result = await query_mcp_server(sql_query=tool_input["sql"], use_tool="execute_sql")
                else:
                    result = {"success": False, "raw": f"Unknown tool: {tool_name}"}
                
                # Add tool result
                tool_results.append({
                    "role": "user", 
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": result.get("raw", str(result))
                    }]
                })
        
        # Continue conversation with tool results
        messages = [
            {"role": "user", "content": f"Student Question: \"{original_question}\"\n\nPlease use the MCP tools to find relevant data and provide a helpful response."},
            {"role": "assistant", "content": response.content}
        ] + tool_results
        
        # Get final response from Claude
        final_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages
        )
        
        return final_response.content[0].text
    
    else:
        # Claude provided a direct response
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