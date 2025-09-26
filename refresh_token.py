#!/usr/bin/env python3
"""
Token refresh script for Honeywell API
Usage: python refresh_token.py [auth_code]
"""
import sys
import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')
API_SECRET = '7bdyEdjGAB5L9vzd'

def exchange_code_for_token(auth_code):
    """Exchange authorization code for access token"""
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    response = requests.post('https://api.honeywellhome.com/oauth2/token',
        headers={
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        data={
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': 'http://localhost:8080/callback'
        })

    if response.ok:
        token_data = response.json()
        access_token = token_data['access_token']

        # Update .env.dev
        with open('.env.dev', 'r') as f:
            content = f.read()

        # Replace token
        lines = content.strip().split('\n')
        new_lines = []
        for line in lines:
            if line.startswith('HONEYWELL_ACCESS_TOKEN='):
                new_lines.append(f'HONEYWELL_ACCESS_TOKEN={access_token}')
            else:
                new_lines.append(line)

        with open('.env.dev', 'w') as f:
            f.write('\n'.join(new_lines) + '\n')

        print(f"✅ New token: {access_token}")
        print("✅ Updated .env.dev")
        print(f"🔑 Update GitHub secret: gh secret set HONEYWELL_ACCESS_TOKEN --body '{access_token}'")
        return access_token
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Auth code provided as argument
        auth_code = sys.argv[1]
        exchange_code_for_token(auth_code)
    else:
        # Interactive mode
        print("🔐 Honeywell Token Refresh")
        print("=" * 40)
        print("\n1️⃣  Visit this URL:")
        print(f"   https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={API_KEY}&redirect_uri=http://localhost:8080/callback")
        print("\n2️⃣  Authorize and get the code from the redirect URL")

        auth_code = input("\n📋 Enter auth code: ").strip()
        if auth_code:
            token = exchange_code_for_token(auth_code)
            if token:
                # Also update GitHub secret automatically
                os.system(f"gh secret set HONEYWELL_ACCESS_TOKEN --body '{token}'")