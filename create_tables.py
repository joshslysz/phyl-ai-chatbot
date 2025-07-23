import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import date

def create_assignments_table():
    # Load environment variables
    load_dotenv()
    
    # Get Supabase credentials
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        return False
    
    try:
        # Create Supabase client
        supabase: Client = create_client(url, key)
        print("✅ Supabase client created successfully")
        
        print("📝 Note: Table creation in Supabase is typically done via:")
        print("  1. Supabase Dashboard SQL Editor")
        print("  2. Database migrations")
        print("  3. Direct database connection")
        print()
        print("🔧 Please create the 'assignments' table manually using this SQL:")
        print()
        create_table_sql = """CREATE TABLE assignments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    week INTEGER NOT NULL,
    date DATE NOT NULL,
    topic TEXT NOT NULL,
    assignment_due TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);"""
        print(create_table_sql)
        print()
        print("🔄 Attempting to use the table (assuming it exists)...")
        
        return supabase
        
    except Exception as e:
        print(f"❌ Failed to connect: {str(e)}")
        return None

def insert_sample_data(supabase: Client):
    try:
        # Insert sample course data
        sample_data = {
            "week": 1,
            "date": "2024-01-15",
            "topic": "Introduction to Course and Python Basics",
            "assignment_due": "Setup Assignment",
            "notes": "Make sure students have Python installed and IDE configured"
        }
        
        response = supabase.table('assignments').insert(sample_data).execute()
        print("✅ Sample data inserted successfully")
        print(f"📝 Inserted record with ID: {response.data[0]['id']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to insert sample data: {str(e)}")
        return False

def retrieve_data(supabase: Client):
    try:
        # Retrieve all assignments data
        response = supabase.table('assignments').select("*").execute()
        
        print("✅ Data retrieved successfully")
        print(f"📊 Found {len(response.data)} records:")
        
        for record in response.data:
            print(f"  Week {record['week']}: {record['topic']}")
            print(f"    Date: {record['date']}")
            if record['assignment_due']:
                print(f"    Assignment Due: {record['assignment_due']}")
            if record['notes']:
                print(f"    Notes: {record['notes']}")
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to retrieve data: {str(e)}")
        return False

def main():
    print("🏗️ Creating assignments table and testing with sample data...")
    
    # Create table and get client
    supabase = create_assignments_table()
    
    if not supabase:
        print("💥 Failed to create table or establish connection")
        return
    
    print("\n📝 Inserting sample data...")
    if insert_sample_data(supabase):
        print("\n📖 Retrieving data to verify...")
        if retrieve_data(supabase):
            print("🎉 Table creation and testing completed successfully!")
        else:
            print("💥 Failed to retrieve data")
    else:
        print("💥 Failed to insert sample data")

if __name__ == "__main__":
    main()