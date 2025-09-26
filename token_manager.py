#!/usr/bin/env python3
"""
Automated token management system
Maintains multiple valid tokens and rotates between them
"""
import requests
import base64
import os
import json
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')
API_SECRET = '7bdyEdjGAB5L9vzd'

class TokenManager:
    def __init__(self):
        self.tokens_file = 'token_store.json'
        self.load_tokens()

    def load_tokens(self):
        """Load stored tokens from file"""
        try:
            with open(self.tokens_file, 'r') as f:
                self.tokens = json.load(f)
        except FileNotFoundError:
            self.tokens = []

    def save_tokens(self):
        """Save tokens to file"""
        with open(self.tokens_file, 'w') as f:
            json.dump(self.tokens, f, indent=2)

    def add_token(self, auth_code):
        """Add a new token from auth code"""
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

            # Store with timestamp
            et = pytz.timezone('US/Eastern')
            created = datetime.now(et).isoformat()

            self.tokens.append({
                'token': access_token,
                'created': created,
                'expires_approx': (datetime.now(et) + timedelta(hours=23)).isoformat()
            })

            self.save_tokens()
            print(f"✅ Added token: {access_token[:20]}...")
            return access_token
        else:
            print(f"❌ Failed to get token: {response.status_code} - {response.text}")
            return None

    def get_valid_token(self):
        """Get the newest valid token, test all if needed"""
        # Sort by creation time, newest first
        sorted_tokens = sorted(self.tokens, key=lambda x: x['created'], reverse=True)

        for token_data in sorted_tokens:
            token = token_data['token']

            # Test token
            test_response = requests.get(
                f'https://api.honeywellhome.com/v2/devices/thermostats/LCC-00D02DB89E33?apikey={API_KEY}&locationId=146016',
                headers={'Authorization': f'Bearer {token}'}
            )

            if test_response.ok:
                print(f"✅ Using valid token: {token[:20]}...")
                return token
            else:
                print(f"❌ Token expired: {token[:20]}...")

        print("❌ No valid tokens available!")
        return None

    def cleanup_expired_tokens(self):
        """Remove expired tokens"""
        valid_tokens = []
        for token_data in self.tokens:
            token = token_data['token']

            # Test token
            test_response = requests.get(
                f'https://api.honeywellhome.com/v2/devices/thermostats/LCC-00D02DB89E33?apikey={API_KEY}&locationId=146016',
                headers={'Authorization': f'Bearer {token}'}
            )

            if test_response.ok:
                valid_tokens.append(token_data)
            else:
                print(f"🗑️  Removing expired token: {token[:20]}...")

        self.tokens = valid_tokens
        self.save_tokens()
        print(f"✅ Cleanup complete, {len(valid_tokens)} tokens remaining")

    def status(self):
        """Show token status"""
        print(f"📊 Token Status: {len(self.tokens)} stored")
        for i, token_data in enumerate(self.tokens, 1):
            created = datetime.fromisoformat(token_data['created'])
            age = datetime.now(pytz.timezone('US/Eastern')) - created
            print(f"  {i}. {token_data['token'][:20]}... (age: {age.total_seconds()/3600:.1f}h)")

if __name__ == "__main__":
    import sys
    tm = TokenManager()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "add" and len(sys.argv) > 2:
            auth_code = sys.argv[2]
            tm.add_token(auth_code)
        elif command == "get":
            token = tm.get_valid_token()
            if token:
                print(token)
        elif command == "cleanup":
            tm.cleanup_expired_tokens()
        elif command == "status":
            tm.status()
        else:
            print("Usage: python token_manager.py [add AUTH_CODE | get | cleanup | status]")
    else:
        tm.status()