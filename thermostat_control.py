import requests
import os
import json
import re
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

def get_working_token():

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
                log_entry(f"Using backup token")
                return token

    except FileNotFoundError:
        pass

    log_entry("Token expired - refresh needed")
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