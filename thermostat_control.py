import requests
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv('.env.dev')

API_KEY = os.getenv('RESIDEO_CONSUMER_KEY')
ACCESS_TOKEN = os.getenv('HONEYWELL_ACCESS_TOKEN')
LOCATION_ID = '146016'
DEVICE_ID = 'LCC-00D02DB89E33'

headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

# Get current status
status_response = requests.get(
    f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
    headers=headers
)

if not status_response.ok:
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    log_entry = f"{now.strftime('%m/%d/%y %H:%M:%S ET')}: ERROR - Cannot get thermostat status: {status_response.status_code}"
    with open('thermostat_log.txt', 'a') as f:
        f.write(log_entry + '\n')
    exit(1)

status = status_response.json()
temp = status['indoorTemperature']
mode = status['changeableValues']['mode']
setpoint = status['changeableValues']['coolSetpoint']
heat_setpoint = status['changeableValues']['heatSetpoint']

et = pytz.timezone('US/Eastern')
now = datetime.now(et)
log = f"{now.strftime('%m/%d/%y %H:%M:%S ET')}: {temp}°F, {mode}, Set:{setpoint}°F"

# Set to 68°F AC if needed
if mode != 'Cool' or setpoint != 68:
    payload = {
        'mode': 'Cool',
        'coolSetpoint': 68,
        'heatSetpoint': heat_setpoint,
        'thermostatSetpointStatus': 'TemporaryHold'
    }

    result = requests.post(
        f'https://api.honeywellhome.com/v2/devices/thermostats/{DEVICE_ID}?apikey={API_KEY}&locationId={LOCATION_ID}',
        headers={**headers, 'Content-Type': 'application/json'},
        json=payload
    )

    if result.ok:
        log += " → SET 68°F AC"
    else:
        log += f" → FAILED: {result.status_code} - {result.text[:100]}"
else:
    log += " → OK"

with open('thermostat_log.txt', 'a') as f:
    f.write(log + '\n')

print(log)