import os
from supabase import create_client, Client
from dotenv import load_dotenv

def test_supabase_connection():
    # Load environment variables
    load_dotenv()
    
    # Get Supabase credentials
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        return False
    
    if url == "your_supabase_url_here" or key == "your_supabase_key_here":
        print("❌ Please update your .env file with actual Supabase credentials")
        print(f"Current URL: {url}")
        print(f"Current KEY: {key[:10]}...")
        return False
    
    try:
        # Create Supabase client
        supabase: Client = create_client(url, key)
        print("✅ Supabase client created successfully")
        print(f"🔗 Connected to: {url}")
        
        # Test connection by making a simple query to a system table
        # Use postgrest health check endpoint or information_schema
        response = supabase.postgrest.session.get('/').json()
        print("✅ Successfully connected to Supabase database")
        print(f"📊 Connection test completed - API is accessible")
        print(f"📈 Postgrest version: {response.get('swagger', 'Unknown')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {str(e)}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Supabase connection...")
    success = test_supabase_connection()
    
    if success:
        print("\n🎉 Supabase connection test passed!")
    else:
        print("\n💥 Supabase connection test failed!")
        print("Please check your credentials in the .env file")