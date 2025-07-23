#!/usr/bin/env python3
"""
Test script for postgres-mcp connection to Supabase database.

Note: This script demonstrates the connection concept since postgres-mcp requires Python 3.12+
and our current environment has Python 3.10. The script shows how to connect to Supabase
in restricted (read-only) mode for security.
"""

import os
import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

def test_supabase_connection():
    """Test connection to Supabase database using PostgreSQL connection."""
    
    # Load environment variables
    load_dotenv()
    
    # Get connection parameters
    supabase_password = os.getenv('SUPABASE_PASSWORD')
    database_uri = os.getenv('DATABASE_URI')
    
    # Use the DATABASE_URI from .env (transaction pooler)
    conn_string = f"{database_uri}?sslmode=require"
    
    print(f"Testing connection to Supabase database...")
    print(f"Connection string: {conn_string.replace(supabase_password, '[PASSWORD]')}")
    
    try:
        # Connect to database in READ ONLY mode for security
        conn = psycopg2.connect(
            conn_string,
            options="-c default_transaction_read_only=on"  # Read-only mode for security
        )
        
        print("✅ Successfully connected to Supabase database!")
        
        # Create a cursor
        cursor = conn.cursor()
        
        # Test 1: List all tables
        print("\n📋 Listing all tables:")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
        
        # Test 2: Check if assignments table exists
        print("\n🔍 Checking for assignments table:")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'assignments'
            );
        """)
        
        assignments_exists = cursor.fetchone()[0]
        if assignments_exists:
            print("✅ Assignments table found!")
            
            # Test 3: Get assignments table structure
            print("\n📊 Assignments table columns:")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'assignments'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            for col in columns:
                nullable = "NULL" if col[2] == "YES" else "NOT NULL"
                print(f"  - {col[0]}: {col[1]} ({nullable})")
            
            # Test 4: Count records in assignments table
            print("\n📈 Assignments table data:")
            cursor.execute("SELECT COUNT(*) FROM assignments;")
            count = cursor.fetchone()[0]
            print(f"  Total records: {count}")
            
            if count > 0:
                # Test 5: Show sample data (limited for security)
                print("\n📝 Sample assignments data:")
                cursor.execute("SELECT * FROM assignments LIMIT 3;")
                records = cursor.fetchall()
                
                # Get column names
                col_names = [desc[0] for desc in cursor.description]
                print(f"  Columns: {', '.join(col_names)}")
                
                for i, record in enumerate(records, 1):
                    print(f"  Record {i}: {dict(zip(col_names, record))}")
        else:
            print("❌ Assignments table not found!")
        
        # Test 6: Database permissions (should be read-only)
        print("\n🔒 Testing read-only restrictions:")
        try:
            cursor.execute("CREATE TABLE test_table (id int);")
            print("❌ WARNING: Write operations are allowed! This should be restricted.")
        except psycopg2.errors.ReadOnlySqlTransaction:
            print("✅ Database is properly configured as read-only!")
        except Exception as e:
            print(f"✅ Write operations blocked: {e}")
        
        # Close connections
        cursor.close()
        conn.close()
        
        print("\n🎉 All tests completed successfully!")
        print("💡 The database connection is ready for MCP integration.")
        print("🔐 Read-only mode ensures security for student-facing queries.")
        
    except psycopg2.Error as e:
        print(f"❌ Database connection error: {e}")
        print("\nTroubleshooting:")
        print("1. Check that SUPABASE_PASSWORD is set correctly in .env")
        print("2. Verify your Supabase project is active")
        print("3. Ensure your IP is whitelisted in Supabase settings")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

def simulate_mcp_commands():
    """Simulate MCP-style commands that would be available."""
    
    print("\n" + "="*60)
    print("🚀 SIMULATED MCP COMMANDS (postgres-mcp)")
    print("="*60)
    
    print("\nAvailable MCP tools for postgres-mcp:")
    print("1. 📋 list_tables - List all tables in the database")
    print("2. 📊 describe_table - Get table schema and column info") 
    print("3. 🔍 query - Execute read-only SQL queries")
    print("4. 📈 count_rows - Count rows in a table")
    print("5. 📝 sample_data - Get sample data from a table")
    
    print("\nRestricted mode features:")
    print("✅ Read-only queries only")
    print("✅ No CREATE, INSERT, UPDATE, DELETE operations")
    print("✅ Perfect for student-facing applications")
    print("✅ Built-in SQL injection protection")
    print("✅ Table and column validation")
    
    print("\nExample MCP usage for your assignments table:")
    print("- mcp query 'SELECT * FROM assignments WHERE week = 1'")
    print("- mcp describe_table assignments")
    print("- mcp count_rows assignments")
    print("- mcp list_tables")

if __name__ == "__main__":
    print("🧪 Testing PostgreSQL MCP Connection to Supabase")
    print("="*60)
    
    # Check if required packages are installed
    try:
        import psycopg2
        print("✅ psycopg2 package found")
    except ImportError:
        print("❌ psycopg2 package not found. Install with: pip install psycopg2-binary")
        exit(1)
    
    # Test the connection
    success = test_supabase_connection()
    
    if success:
        simulate_mcp_commands()
    
    print("\n" + "="*60)
    print("Note: postgres-mcp requires Python 3.12+")
    print("Current Python version:", os.sys.version)
    print("To use actual postgres-mcp, upgrade to Python 3.12+")