import requests
import os
import json
import re
from datetime import datetime
import pytz
from dotenv import load_dotenv

if os.path.exists('.env.dev'):
    load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')
ACCESS_TOKEN = os.getenv('HONEYWELL_ACCESS_TOKEN')
LOCATION_ID = '146016'
DEVICE_ID = 'LCC-00D02DB89E33'
TARGET_TEMP = 68
TARGET_HEAT_TEMP = 67

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
    if not ACCESS_TOKEN:
        log_entry("ERROR: No access token available")
        exit(1)

    test_response = requests.get(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}
    )

    if test_response.ok:
        return ACCESS_TOKEN

    log_entry("ERROR: Access token is invalid")
    exit(1)

def get_thermostat_status():
    """Get current thermostat status including temperature and settings."""
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

    status_response = requests.get(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers=headers
    )

    if not status_response.ok:
        log_entry(f"ERROR: Cannot get thermostat status")
        exit(1)

    status = status_response.json()
    return {
        'temperature': status['indoorTemperature'],
        'mode': status['changeableValues']['mode'],
        'cool_setpoint': status['changeableValues']['coolSetpoint'],
        'heat_setpoint': status['changeableValues']['heatSetpoint']
    }

def set_thermostat(desired_mode, desired_cool_setpoint, desired_heat_setpoint, current_status):
    """Set thermostat mode and temperature setpoints if they differ from current values."""
    current_mode = current_status['mode']
    current_cool = current_status['cool_setpoint']
    current_heat = current_status['heat_setpoint']

    # Check if we need to make changes
    if (current_mode == desired_mode and
        current_cool == desired_cool_setpoint and
        current_heat == desired_heat_setpoint):
        return None  # No change needed

    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

    payload = {
        'mode': desired_mode,
        'coolSetpoint': desired_cool_setpoint,
        'heatSetpoint': desired_heat_setpoint,
        'thermostatSetpointStatus': 'TemporaryHold'
    }

    result = requests.post(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers={**headers, 'Content-Type': 'application/json'},
        json=payload
    )

    return result.ok

ACCESS_TOKEN = get_working_token()

# Get current status
status = get_thermostat_status()
temp = status['temperature']
mode = status['mode']
cool_setpoint = status['cool_setpoint']
heat_setpoint = status['heat_setpoint']

message = f"{temp}°F, {mode}, Cool:{cool_setpoint}°F, Heat:{heat_setpoint}°F"

# Determine desired mode based on current temperature
if temp > TARGET_TEMP:
    # Too hot - use cooling
    result = set_thermostat('Cool', TARGET_TEMP, heat_setpoint, status)
    if result is None:
        message += " → OK"
    elif result:
        message += f" → SET COOL {TARGET_TEMP}°F"
    else:
        message += f" → ERROR"
elif temp < TARGET_HEAT_TEMP:
    # Too cold - use heating
    result = set_thermostat('Heat', cool_setpoint, TARGET_HEAT_TEMP, status)
    if result is None:
        message += " → OK"
    elif result:
        message += f" → SET HEAT {TARGET_HEAT_TEMP}°F"
    else:
        message += f" → ERROR"
else:
    # Temperature is within acceptable range (67-68°F)
    message += " → OK (within range)"

log_entry(message)