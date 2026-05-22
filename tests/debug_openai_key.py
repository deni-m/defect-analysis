"""Debug script to compare .env loading methods."""
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from openai import OpenAI

print("=" * 60)
print("DEBUGGING OPENAI API KEY LOADING")
print("=" * 60)

# Test 1: Load from .env
print("\n1. Loading from .env file...")
load_dotenv()
key_from_env = os.getenv("OPENAI_API_KEY")

if not key_from_env:
    print("❌ No key found!")
    sys.exit(1)

print(f"✓ Key found: length={len(key_from_env)}")
print(f"✓ Starts with: {key_from_env[:15]}")
print(f"✓ Ends with: ...{key_from_env[-20:]}")

# Test 2: Check for invisible characters
print("\n2. Checking for invisible characters...")
print(f"   Has \\n: {repr(key_from_env).count('\\n')}")
print(f"   Has \\r: {repr(key_from_env).count('\\r')}")
print(f"   Has \\t: {repr(key_from_env).count('\\t')}")
print(f"   Leading/trailing spaces: '{key_from_env[:5]}' ... '{key_from_env[-5:]}'")

# Test 3: Clean the key
print("\n3. Cleaning the key...")
cleaned_key = key_from_env.strip().replace('\n', '').replace('\r', '').replace(' ', '')
print(f"   Original length: {len(key_from_env)}")
print(f"   Cleaned length: {len(cleaned_key)}")
print(f"   Difference: {len(key_from_env) - len(cleaned_key)} chars removed")

# Test 4: Try with cleaned key
print("\n4. Testing with CLEANED key...")
try:
    client = OpenAI(api_key=cleaned_key)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )
    print(f"✅ SUCCESS with cleaned key!")
    print(f"   Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ FAILED with cleaned key: {e}")

# Test 5: Try with original key
print("\n5. Testing with ORIGINAL key...")
try:
    client = OpenAI(api_key=key_from_env)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )
    print(f"✅ SUCCESS with original key!")
    print(f"   Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ FAILED with original key: {e}")

print("\n" + "=" * 60)
print("DIAGNOSIS:")
if len(key_from_env) != len(cleaned_key):
    print(f"⚠️  Your .env file has {len(key_from_env) - len(cleaned_key)} hidden characters!")
    print("   Fix: Remove any spaces, newlines, or tabs from the key in .env")
else:
    print("✓ Key format looks clean")
print("=" * 60)
