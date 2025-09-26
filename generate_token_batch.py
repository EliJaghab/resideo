#!/usr/bin/env python3
"""
Generate multiple auth URLs for batch token creation
Run this script to get multiple authorization URLs, then visit each one to get auth codes
"""
import os
from dotenv import load_dotenv

load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')

print("🔐 Batch Token Generator")
print("=" * 50)
print("\nTo create multiple backup tokens, visit these URLs one by one:")
print("(You can do this all at once, or spread it out over time)")
print()

for i in range(1, 6):  # Generate 5 URLs
    url = f"https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={API_KEY}&redirect_uri=http://localhost:8080/callback"
    print(f"{i}. {url}")

print("\n📋 For each URL:")
print("   1. Visit the URL in a new tab/window")
print("   2. Authorize the app")
print("   3. Copy the 'code' from the redirect URL")
print("   4. Run: python token_manager.py add YOUR_CODE_HERE")

print(f"\n🔄 Quick add commands:")
for i in range(1, 6):
    print(f"   python token_manager.py add CODE_{i}")

print(f"\n📊 Check status anytime: python token_manager.py status")
print(f"🧹 Clean expired: python token_manager.py cleanup")