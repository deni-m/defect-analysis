"""Quick test script to verify OpenAI API connection."""
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
print("Loading .env file...")
load_dotenv()

# Get API key
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ OPENAI_API_KEY not found in environment")
    print("\nCheck:")
    print("1. .env file exists in project root")
    print("2. Contains line: OPENAI_API_KEY=sk-...")
    sys.exit(1)

print(f"✓ API key found (length: {len(api_key)} chars)")
print(f"✓ Key starts with: {api_key[:10]}...")

# Check for newlines (common issue)
if '\n' in api_key or '\r' in api_key:
    print("❌ WARNING: API key contains newline characters!")
    print("   This will cause 401 errors. Remove line breaks from .env file.")
    sys.exit(1)

# Check for spaces
if api_key != api_key.strip():
    print("⚠️  WARNING: API key has leading/trailing whitespace")
    api_key = api_key.strip()
    print(f"   Trimmed to length: {len(api_key)}")

print("\n--- Testing OpenAI Connection ---")

# Try to connect
try:
    client = OpenAI(api_key=api_key)
    print(f"✓ Client created")
    
    print("✓ Sending test request to gpt-3.5-turbo...")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Say 'test'"}],
        max_tokens=5
    )
    print(f"✓ Connection successful!")
    print(f"✓ Response: {response.choices[0].message.content}")
    print("\n✅ OpenAI API is working correctly!")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print(f"\nError type: {type(e).__name__}")
    
    if "401" in str(e):
        print("\n401 Unauthorized - Common causes:")
        print("1. Invalid API key - verify it's correct on https://platform.openai.com/api-keys")
        print("2. API key expired or revoked")
        print("3. Insufficient quota/credits on your OpenAI account")
        print("4. Check if you have access to the model you're trying to use")
    elif "429" in str(e):
        print("\n429 Rate Limit - You've exceeded your rate limit")
    else:
        print("\nOther common issues:")
        print("- Network/firewall blocking api.openai.com")
        print("- Proxy configuration issues")
    
    sys.exit(1)
