#!/usr/bin/env python3
"""
Fully automated OAuth flow with headless browser
Handles login, 2FA, and token generation automatically
"""
import os
import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv

load_dotenv('.env.dev')

class HoneywellOAuthBot:
    def __init__(self):
        self.api_key = os.getenv('RESIDEO_CONSUMER_KEY')
        self.api_secret = '7bdyEdjGAB5L9vzd'
        self.username = os.getenv('HONEYWELL_USERNAME')
        self.password = os.getenv('HONEYWELL_PASSWORD')
        self.totp_secret = os.getenv('HONEYWELL_TOTP_SECRET')  # For 2FA

        # Setup headless Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 30)

    def generate_totp_code(self):
        """Generate TOTP code for 2FA"""
        if not self.totp_secret:
            return None

        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()

    def perform_oauth_flow(self):
        """Complete OAuth flow automatically"""
        try:
            # 1. Navigate to OAuth authorization URL
            auth_url = f"https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={self.api_key}&redirect_uri=http://localhost:8080/callback"
            print(f"🌐 Navigating to: {auth_url}")
            self.driver.get(auth_url)

            # 2. Fill in username
            print("👤 Entering username...")
            username_field = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
            username_field.clear()
            username_field.send_keys(self.username)

            # 3. Fill in password
            print("🔒 Entering password...")
            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(self.password)

            # 4. Submit login form
            print("✅ Submitting login...")
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            login_button.click()

            # 5. Handle 2FA if required
            try:
                print("🔐 Checking for 2FA prompt...")
                totp_field = self.wait.until(EC.presence_of_element_located((By.ID, "totpCode")), timeout=10)

                if self.totp_secret:
                    totp_code = self.generate_totp_code()
                    print(f"📱 Entering 2FA code: {totp_code}")
                    totp_field.clear()
                    totp_field.send_keys(totp_code)

                    # Submit 2FA
                    totp_submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                    totp_submit.click()
                else:
                    print("❌ 2FA required but no TOTP secret provided")
                    return None

            except TimeoutException:
                print("ℹ️  No 2FA required, proceeding...")

            # 6. Wait for authorization page and accept
            print("📋 Looking for authorization consent...")
            try:
                # Look for common consent button text
                consent_selectors = [
                    "//button[contains(text(), 'Allow')]",
                    "//button[contains(text(), 'Authorize')]",
                    "//button[contains(text(), 'Accept')]",
                    "//input[@value='Allow']",
                    "//input[@value='Authorize']"
                ]

                consent_button = None
                for selector in consent_selectors:
                    try:
                        consent_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)), timeout=5)
                        break
                    except TimeoutException:
                        continue

                if consent_button:
                    print("✅ Clicking authorization consent...")
                    consent_button.click()
                else:
                    print("ℹ️  No consent screen found, checking for redirect...")

            except TimeoutException:
                print("ℹ️  No consent screen, checking current URL...")

            # 7. Wait for redirect and extract code
            print("🔗 Waiting for OAuth callback...")
            WebDriverWait(self.driver, 30).until(
                lambda driver: "localhost:8080/callback" in driver.current_url or "code=" in driver.current_url
            )

            current_url = self.driver.current_url
            print(f"📍 Redirected to: {current_url}")

            # Extract authorization code
            if "code=" in current_url:
                auth_code = current_url.split("code=")[1].split("&")[0]
                print(f"🎯 Extracted auth code: {auth_code}")
                return auth_code
            else:
                print("❌ No authorization code found in redirect URL")
                return None

        except Exception as e:
            print(f"❌ OAuth flow failed: {str(e)}")
            return None
        finally:
            self.driver.quit()

    def exchange_code_for_token(self, auth_code):
        """Exchange authorization code for access token"""
        credentials = f"{self.api_key}:{self.api_secret}"
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
            print(f"✅ Got access token: {access_token[:20]}...")
            return access_token
        else:
            print(f"❌ Token exchange failed: {response.status_code} - {response.text}")
            return None

    def full_token_refresh(self):
        """Complete end-to-end automated token refresh"""
        print("🚀 Starting automated OAuth token refresh...")

        # Perform OAuth flow
        auth_code = self.perform_oauth_flow()
        if not auth_code:
            return None

        # Exchange for token
        access_token = self.exchange_code_for_token(auth_code)
        if not access_token:
            return None

        print("🎉 Automated token refresh successful!")
        return access_token

if __name__ == "__main__":
    bot = HoneywellOAuthBot()
    token = bot.full_token_refresh()
    if token:
        print(f"New token: {token}")
    else:
        print("Failed to get new token")