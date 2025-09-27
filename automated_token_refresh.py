#!/usr/bin/env python3
import os
import sys
import time
import base64
import requests
import subprocess
import re
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
    message = str(message)
    message = re.sub(r'[A-Za-z0-9]{28,}', '***', message)
    message = re.sub(r'code=[A-Za-z0-9]{6,12}', 'code=***', message)
    message = re.sub(r'client_id=[^&\s]+', 'client_id=***', message)
    message = re.sub(r'Bearer [A-Za-z0-9]+', 'Bearer ***', message)

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
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')
    username = os.getenv('HONEYWELL_USERNAME')
    password = os.getenv('HONEYWELL_PASSWORD')
    totp_secret = os.getenv('HONEYWELL_TOTP_SECRET')

    if not all([api_key, username, password]):
        return None

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
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 30)

        auth_url = f"https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={api_key}&redirect_uri=http://localhost:8080/callback"
        driver.get(auth_url)

        username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        username_field.clear()
        username_field.send_keys(username)

        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys(password)

        form = driver.find_element(By.ID, "validate-form")
        form.submit()

        try:
            totp_wait = WebDriverWait(driver, 5)
            totp_field = totp_wait.until(EC.presence_of_element_located((By.ID, "totpCode")))
            if totp_secret:
                code = generate_totp_code(totp_secret)
                totp_field.send_keys(code)
                totp_submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                totp_submit.click()
            else:
                return None
        except TimeoutException:
            pass

        try:
            consent_wait = WebDriverWait(driver, 10)
            consent_button = consent_wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "allowButton")))
            try:
                driver.execute_script("arguments[0].click();", consent_button)
                time.sleep(3)
            except:
                try:
                    consent_button.click()
                    time.sleep(3)
                except:
                    pass
        except TimeoutException:
            pass

        try:
            device_wait = WebDriverWait(driver, 10)
            connect_button = device_wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "connect")))
            driver.execute_script("arguments[0].click();", connect_button)
            time.sleep(2)
        except TimeoutException:
            pass

        wait.until(lambda d: "localhost:8080/callback" in d.current_url or "code=" in d.current_url)

        current_url = driver.current_url
        if "code=" in current_url:
            auth_code = current_url.split("code=")[1].split("&")[0]
            return auth_code
        else:
            return None

    except Exception as e:
        log_entry("ERROR: Token refresh failed")
        return None
    finally:
        if driver:
            driver.quit()

def exchange_code_for_token(auth_code):
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')
    api_secret = os.getenv('RESIDEO_CONSUMER_SECRET')
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
        return token_data['access_token']
    return None

def update_github_secret(token):
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        return False

    result = subprocess.run(
        ['gh', 'secret', 'set', 'HONEYWELL_ACCESS_TOKEN', '--body', token],
        capture_output=True,
        text=True,
        env=dict(os.environ, GH_TOKEN=github_token)
    )
    return result.returncode == 0

def main():
    current_token = os.getenv('HONEYWELL_ACCESS_TOKEN')
    api_key = os.getenv('RESIDEO_CONSUMER_KEY')

    if current_token and test_token(current_token, api_key):
        return 0

    auth_code = perform_oauth_login()
    if not auth_code:
        log_entry("ERROR: Token refresh failed")
        return 1

    new_token = exchange_code_for_token(auth_code)
    if not new_token:
        log_entry("ERROR: Token refresh failed")
        return 1

    if not test_token(new_token, api_key):
        log_entry("ERROR: Token refresh failed")
        return 1

    if os.getenv('GITHUB_TOKEN'):
        update_github_secret(new_token)

    try:
        with open('.env.dev', 'r') as f:
            lines = f.readlines()
        with open('.env.dev', 'w') as f:
            for line in lines:
                if line.startswith('HONEYWELL_ACCESS_TOKEN='):
                    f.write(f'HONEYWELL_ACCESS_TOKEN={new_token}\n')
                else:
                    f.write(line)
    except:
        pass

    log_entry("Token refreshed")
    return 0

if __name__ == "__main__":
    sys.exit(main())