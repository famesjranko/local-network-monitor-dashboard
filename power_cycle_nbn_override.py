import asyncio
import tapo
import json  # Importing json for pretty printing the output
import logging
import sqlite3
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0])) 

# Set up logging configuration
logging.basicConfig(
    filename=os.path.join(SCRIPT_DIR, 'logs/check_internet.log'),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Your Tapo credentials and IP address
email = "example@example.com"
password = "password"
device_ip = "device_ip_address"
device_name = "device_name"

# The time to wait between turning off and on the device (in seconds)
wait_time = 30  # You can change this to any number of seconds
retry_attempts = 3  # Number of retries if a connection fails

# Log power cycle event to SQLite database
def log_power_cycle_event(reason="Internet down for 5+ minutes"):
    try:   
        db_file = os.path.join(SCRIPT_DIR, 'logs/internet_status.db')
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO power_cycle_events (timestamp, reason) VALUES (?, ?)",
                       (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reason))
        conn.commit()
        conn.close()
        logging.info("Power cycle event logged successfully.")
    except sqlite3.Error as e:
        logging.error(f"Failed to log power cycle event: {e}")

async def control_tapo():
    try:
        # Initialize API client
        client = tapo.ApiClient(email, password)

        # Get the P100 device (requires `await`)
        device = await client.p100(device_ip)

        # Refresh the session (useful if connection becomes inactive)
        await device.refresh_session()
        print(f"Session refreshed for {device_name}.")

        # Turn off the device
        await device.off()
        print(f"{device_name} has been turned off.")
        logging.info(f"OVERIDE: {device_name} has been turned off.")

        # Wait for the specified period
        await asyncio.sleep(wait_time)
        print(f"Waited for {wait_time} seconds.")

        # Turn the device back on
        await device.on()
        print(f"{device_name} has been turned back on.")
        logging.info(f"OVERIDE: {device_name} has been turned on.")

        # Log the power cycle event
        log_power_cycle_event("manually triggered")

        # Print device info after successful operation
        await print_device_info(device)

    except asyncio.TimeoutError:
        print("The request timed out. Please check your network connection or the device.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        await handle_exception(device)

async def handle_exception(device):
    # Retry logic on exception
    for attempt in range(1, retry_attempts + 1):
        try:
            print(f"Attempting to refresh session and retry... (Attempt {attempt}/{retry_attempts})")
            logging.info(f"OVERIDE: Attempting to refresh session and retry... (Attempt {attempt}/{retry_attempts}).")
            await device.refresh_session()

            # Try to turn the device on after failure
            await device.on()
            print(f"{device_name} has been turned back on after retry attempt {attempt}.")
            logging.info(f"OVERIDE: {device_name} has been turned back on after retry attempt {attempt}.")

            # Print device info after successful retry
            await print_device_info(device)
            return  # Exit the loop if successful
        except Exception as retry_error:
            print(f"Retry attempt {attempt} failed: {retry_error}")
            if attempt == retry_attempts:
                print(f"All retry attempts failed. Please check your connection.")
                logging.info(f"OVERIDE: All retry attempts failed. Please check your connection.")
                return

async def print_device_info(device):
    try:
        # Get additional device information in JSON format
        device_info_json = await device.get_device_info_json()

        # Pretty print the JSON response
        pretty_device_info = json.dumps(device_info_json, indent=4)
        print(f"Device Info:\n{pretty_device_info}")
    except Exception as e:
        print(f"Failed to retrieve device info: {e}")

# Run the async function
asyncio.run(control_tapo())
