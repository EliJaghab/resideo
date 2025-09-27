#!/usr/bin/env python3
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
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

load_dotenv('.env.dev')

def log_entry(message):
    et = pytz.timezone('US/Eastern')
    timestamp = datetime.now(et).strftime('%m/%d/%y %H:%M:%S ET')
    entry = f"{timestamp}: {message}"
    with open('thermostat_log.txt', 'a') as f:
        f.write(entry + '\n')
    print(entry)

def generate_totp_code(secret):
    import pyotp
    totp = pyotp.TOTP(secret)
    return totp.now()

def test_token(token, api_key):
    response = requests.get(
        f'https://api.honeywellhome.com/v2/devices/thermostats/LCC-00D02DB89E33?apikey={api_key}&locationId=146016',
        headers={'Authorization': f'Bearer {token}'}
    )
    return response.ok

def perform_oauth_login():

    # Get credentials
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')
    username = os.getenv('HONEYWELL_USERNAME')
    password = os.getenv('HONEYWELL_PASSWORD')
    totp_secret = os.getenv('HONEYWELL_TOTP_SECRET')

    if not all([api_key, username, password]):
        log_entry("Missing required credentials (username/password)")
        return None

    # Setup headless Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    driver = None
    try:
        # Use webdriver-manager for automatic ChromeDriver management
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 30)

        # Navigate to OAuth URL
        auth_url = f"https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={api_key}&redirect_uri=http://localhost:8080/callback"
        log_entry("Starting automated OAuth flow...")
        driver.get(auth_url)

        # Enter username and password
        log_entry("Entering credentials...")

        # Wait for username field
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        username_field.clear()
        username_field.send_keys(username)

        # Enter password
        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys(password)

        # Submit form - find the form and submit it
        form = driver.find_element(By.ID, "validate-form")
        form.submit()

        # Handle 2FA if needed
        try:
            totp_wait = WebDriverWait(driver, 5)
            totp_field = totp_wait.until(EC.presence_of_element_located((By.ID, "totpCode")))
            if totp_secret:
                code = generate_totp_code(totp_secret)
                log_entry("Entering 2FA code...")
                totp_field.send_keys(code)
                totp_submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                totp_submit.click()
            else:
                log_entry("2FA required but no TOTP secret provided")
                return None
        except TimeoutException:
            pass  # No 2FA required

        # Handle consent screen
        try:
            log_entry("Looking for consent screen...")
            consent_wait = WebDriverWait(driver, 10)
            # Look for the Allow button by class name
            consent_button = consent_wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, "allowButton"))
            )
            log_entry("Clicking Allow on consent screen...")

            # Try clicking with JavaScript to ensure proper event handling
            try:
                # Use JavaScript to click the button (ensures all event handlers fire)
                driver.execute_script("arguments[0].click();", consent_button)
                log_entry("Clicked Allow button via JavaScript")
                time.sleep(3)  # Give more time for the redirect

            except Exception as e:
                log_entry(f"JavaScript click failed: {str(e)}")
                # Fallback to regular click
                try:
                    consent_button.click()
                    time.sleep(3)
                except Exception as e2:
                    log_entry(f"Regular click also failed: {str(e2)}")

        except TimeoutException:
            log_entry("No consent screen found")
            pass  # No consent needed

        # Handle device selection page
        try:
            log_entry("Looking for device selection page...")
            device_wait = WebDriverWait(driver, 10)
            # Look for the Connect button on device selection page
            connect_button = device_wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, "connect"))
            )
            log_entry("Found device selection page - clicking Connect...")

            # The checkbox should already be checked by default, just click Connect
            driver.execute_script("arguments[0].click();", connect_button)
            log_entry("Clicked Connect button")
            time.sleep(2)

        except TimeoutException:
            log_entry("No device selection page found")
            pass  # No device selection needed

        # Wait for redirect
        log_entry("Waiting for OAuth callback...")
        wait.until(lambda d: "localhost:8080/callback" in d.current_url or "code=" in d.current_url)

        # Extract auth code
        current_url = driver.current_url
        log_entry(f"Final URL: {current_url}")

        if "code=" in current_url:
            auth_code = current_url.split("code=")[1].split("&")[0]
            log_entry(f"Got authorization code: {auth_code}")
            return auth_code
        else:
            log_entry("No authorization code in redirect")
            return None

    except Exception as e:
        log_entry(f"OAuth flow failed: {str(e)}")
        return None
    finally:
        if driver:
            driver.quit()

def exchange_code_for_token(auth_code):
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
        log_entry("Successfully exchanged code for access token")
        return access_token
    else:
        log_entry(f"Token exchange failed: {response.status_code}")
        return None

def update_github_secret(token):
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        log_entry("No GITHUB_TOKEN available for updating secret")
        return False

    result = subprocess.run(
        ['gh', 'secret', 'set', 'HONEYWELL_ACCESS_TOKEN', '--body', token],
        capture_output=True,
        text=True,
        env=dict(os.environ, GH_TOKEN=github_token)
    )

    if result.returncode == 0:
        log_entry("Updated GitHub secret HONEYWELL_ACCESS_TOKEN")
        return True
    else:
        log_entry(f"Failed to update GitHub secret: {result.stderr}")
        return False

def main():
    log_entry("Starting automated token refresh check...")

    # Check current token
    current_token = os.getenv('HONEYWELL_ACCESS_TOKEN')
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')

    if current_token and test_token(current_token, api_key):
        log_entry("Current token is still valid - no refresh needed")
        return 0

    log_entry("Token expired or invalid - starting automated refresh...")

    # Perform OAuth flow
    auth_code = perform_oauth_login()
    if not auth_code:
        log_entry("Failed to get authorization code")
        return 1

    # Exchange for token
    new_token = exchange_code_for_token(auth_code)
    if not new_token:
        log_entry("Failed to get access token")
        return 1

    # Test new token
    if not test_token(new_token, api_key):
        log_entry("New token failed validation")
        return 1

    # Update GitHub secret if running in GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        if update_github_secret(new_token):
            log_entry("Fully automated token refresh complete!")
        else:
            log_entry("Token refreshed but GitHub secret update failed")
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

        log_entry("Updated local .env.dev with new token")
        print(f"\nTo update GitHub secret, run:")
        print("gh secret set HONEYWELL_ACCESS_TOKEN --body '<NEW_TOKEN>'")

    return 0

if __name__ == "__main__":
    sys.exit(main())