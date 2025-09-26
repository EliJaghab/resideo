#!/usr/bin/env python3
"""
Standalone automated token refresh using headless browser
This script handles the complete OAuth flow automatically
"""
import os
import sys
import time
import base64
import requests
import subprocess
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

load_dotenv('.env.dev')

def log_entry(message):
    """Log with timestamp to thermostat_log.txt"""
    et = pytz.timezone('US/Eastern')
    timestamp = datetime.now(et).strftime('%m/%d/%y %H:%M:%S ET')
    entry = f"{timestamp}: {message}"
    with open('thermostat_log.txt', 'a') as f:
        f.write(entry + '\n')
    print(entry)

def generate_totp_code(secret):
    """Generate TOTP code for 2FA"""
    import pyotp
    totp = pyotp.TOTP(secret)
    return totp.now()

def test_token(token, api_key):
    """Test if a token is valid"""
    response = requests.get(
        f'https://api.honeywellhome.com/v2/devices/thermostats/LCC-00D02DB89E33?apikey={api_key}&locationId=146016',
        headers={'Authorization': f'Bearer {token}'}
    )
    return response.ok

def perform_oauth_login():
    """Perform automated OAuth login with headless browser"""

    # Get credentials
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')
    username = os.getenv('HONEYWELL_USERNAME')
    password = os.getenv('HONEYWELL_PASSWORD')
    totp_secret = os.getenv('HONEYWELL_TOTP_SECRET')

    if not all([api_key, username, password]):
        log_entry("❌ Missing required credentials (username/password)")
        return None

    # Setup headless Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 30)

        # Navigate to OAuth URL
        auth_url = f"https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={api_key}&redirect_uri=http://localhost:8080/callback"
        log_entry("🌐 Starting automated OAuth flow...")
        driver.get(auth_url)

        # Enter username
        log_entry("👤 Entering credentials...")
        username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        username_field.send_keys(username)

        # Enter password
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(password)

        # Submit login
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        # Handle 2FA if needed
        try:
            totp_field = wait.until(EC.presence_of_element_located((By.ID, "totpCode")), timeout=5)
            if totp_secret:
                code = generate_totp_code(totp_secret)
                log_entry("🔐 Entering 2FA code...")
                totp_field.send_keys(code)
                totp_submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                totp_submit.click()
            else:
                log_entry("❌ 2FA required but no TOTP secret provided")
                return None
        except TimeoutException:
            pass  # No 2FA required

        # Handle consent screen
        try:
            consent_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow') or contains(text(), 'Authorize')]")),
                timeout=5
            )
            consent_button.click()
        except TimeoutException:
            pass  # No consent needed

        # Wait for redirect
        log_entry("🔗 Waiting for OAuth callback...")
        wait.until(lambda d: "localhost:8080/callback" in d.current_url or "code=" in d.current_url)

        # Extract auth code
        current_url = driver.current_url
        if "code=" in current_url:
            auth_code = current_url.split("code=")[1].split("&")[0]
            log_entry(f"✅ Got authorization code")
            return auth_code
        else:
            log_entry("❌ No authorization code in redirect")
            return None

    except Exception as e:
        log_entry(f"❌ OAuth flow failed: {str(e)}")
        return None
    finally:
        if driver:
            driver.quit()

def exchange_code_for_token(auth_code):
    """Exchange authorization code for access token"""
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')
    api_secret = '7bdyEdjGAB5L9vzd'

    credentials = f"{api_key}:{api_secret}"
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
        log_entry("✅ Successfully exchanged code for access token")
        return access_token
    else:
        log_entry(f"❌ Token exchange failed: {response.status_code}")
        return None

def update_github_secret(token):
    """Update GitHub secret with new token"""
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        log_entry("❌ No GITHUB_TOKEN available for updating secret")
        return False

    result = subprocess.run(
        ['gh', 'secret', 'set', 'HONEYWELL_ACCESS_TOKEN', '--body', token],
        capture_output=True,
        text=True,
        env=dict(os.environ, GH_TOKEN=github_token)
    )

    if result.returncode == 0:
        log_entry("✅ Updated GitHub secret HONEYWELL_ACCESS_TOKEN")
        return True
    else:
        log_entry(f"❌ Failed to update GitHub secret: {result.stderr}")
        return False

def main():
    """Main automated token refresh flow"""
    log_entry("🤖 Starting automated token refresh check...")

    # Check current token
    current_token = os.getenv('HONEYWELL_ACCESS_TOKEN')
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')

    if current_token and test_token(current_token, api_key):
        log_entry("✅ Current token is still valid - no refresh needed")
        return 0

    log_entry("⏰ Token expired or invalid - starting automated refresh...")

    # Perform OAuth flow
    auth_code = perform_oauth_login()
    if not auth_code:
        log_entry("❌ Failed to get authorization code")
        return 1

    # Exchange for token
    new_token = exchange_code_for_token(auth_code)
    if not new_token:
        log_entry("❌ Failed to get access token")
        return 1

    # Test new token
    if not test_token(new_token, api_key):
        log_entry("❌ New token failed validation")
        return 1

    # Update GitHub secret if running in GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        if update_github_secret(new_token):
            log_entry("🎉 Fully automated token refresh complete!")
        else:
            log_entry("⚠️  Token refreshed but GitHub secret update failed")
    else:
        # Update local .env.dev
        with open('.env.dev', 'r') as f:
            lines = f.readlines()

        with open('.env.dev', 'w') as f:
            for line in lines:
                if line.startswith('HONEYWELL_ACCESS_TOKEN='):
                    f.write(f'HONEYWELL_ACCESS_TOKEN={new_token}\n')
                else:
                    f.write(line)

        log_entry("✅ Updated local .env.dev with new token")
        print(f"\n📋 To update GitHub secret, run:")
        print(f"gh secret set HONEYWELL_ACCESS_TOKEN --body '{new_token}'")

    return 0

if __name__ == "__main__":
    sys.exit(main())