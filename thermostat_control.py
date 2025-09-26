import requests
import os
import json
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')
ACCESS_TOKEN = os.getenv('HONEYWELL_ACCESS_TOKEN')
LOCATION_ID = '146016'
DEVICE_ID = 'LCC-00D02DB89E33'
TARGET_TEMP = 68

def log_entry(message):
    et = pytz.timezone('US/Eastern')
    timestamp = datetime.now(et).strftime('%m/%d/%y %H:%M:%S ET')
    entry = f"{timestamp}: {message}"
    with open('thermostat_log.txt', 'a') as f:
        f.write(entry + '\n')
    print(entry)

def get_working_token():

    # Try current env token first
    test_response = requests.get(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}
    )

    if test_response.ok:
        return ACCESS_TOKEN

    # Try stored tokens
    try:
        with open('token_store.json', 'r') as f:
            tokens = json.load(f)

        # Sort by creation time, newest first
        sorted_tokens = sorted(tokens, key=lambda x: x['created'], reverse=True)

        for token_data in sorted_tokens:
            token = token_data['token']
            test_response = requests.get(
                f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
                headers={'Authorization': f'Bearer {token}'}
            )

            if test_response.ok:
                log_entry(f"Using backup token: {token[:20]}...")
                return token

    except FileNotFoundError:
        pass

    log_entry("ALL TOKENS EXPIRED - Generate new ones!")
    log_entry("Run: python automated_token_refresh.py")
    log_entry(f"Auth URL: https://api.honeywellhome.com/oauth2/authorize?response_type=code&client_id={API_KEY}&redirect_uri=http://localhost:8080/callback")
    exit(1)

ACCESS_TOKEN = get_working_token()
headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

# Get current status
status_response = requests.get(
    f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
    headers=headers
)

if not status_response.ok:
    log_entry(f"ERROR - Cannot get thermostat status: {status_response.status_code}")
    exit(1)

status = status_response.json()
temp = status['indoorTemperature']
mode = status['changeableValues']['mode']
cool_setpoint = status['changeableValues']['coolSetpoint']
heat_setpoint = status['changeableValues']['heatSetpoint']

message = f"{temp}°F, {mode}, Set:{cool_setpoint}°F"

# Set to 68°F AC if needed
if mode != 'Cool' or cool_setpoint != TARGET_TEMP:
    payload = {
        'mode': 'Cool',
        'coolSetpoint': TARGET_TEMP,
        'heatSetpoint': heat_setpoint,
        'thermostatSetpointStatus': 'TemporaryHold'
    }

    result = requests.post(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers={**headers, 'Content-Type': 'application/json'},
        json=payload
    )

    if result.ok:
        message += f" → SET {TARGET_TEMP}°F AC"
    else:
        message += f" → FAILED: {result.status_code} - {result.text[:100]}"
else:
    message += " → OK"

log_entry(message)