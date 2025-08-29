#!/usr/bin/env python3
"""
Aranet4 Historical Data Recovery Script
Retrieves stored historical data from Aranet4 device and writes to InfluxDB
"""

import aranet4
import datetime
import logging
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
import os
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/greg/repos/sensors/aranet_recovery.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# InfluxDB Configuration (from .env file)
INFLUX_URL = os.environ.get("INFLUX_URL")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = os.environ.get("INFLUX_ORG")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET")

# Aranet4 Configuration (from .env file)
ARANET_MAC = os.environ.get("ARANET_MAC")
DEVICE_NAME = os.environ.get("DEVICE_NAME")
LOCATION = os.environ.get("LOCATION")

def c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit"""
    return celsius * 9.0 / 5.0 + 32.0

def get_historical_data():
    """Retrieve all historical data from Aranet4 device"""
    try:
        logger.info(f"Connecting to Aranet4 device: {ARANET_MAC}")
        
        # Get all historical records from the device
        history = aranet4.client.get_all_records(ARANET_MAC)
        
        logger.info(f"Retrieved {len(history.value)} historical records")
        return history.value
        
    except Exception as e:
        logger.error(f"Failed to retrieve historical data: {e}")
        raise

def write_historical_to_influx(records):
    """Write historical records to InfluxDB"""
    if not records:
        logger.info("No historical records to write")
        return
        
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        points = []
        for record in records:
            # Skip invalid readings
            if record.co2 <= 0 or record.temperature < -50 or record.temperature > 80:
                logger.warning(f"Skipping invalid reading: CO2={record.co2}, Temp={record.temperature}")
                continue
                
            temp_f = c_to_f(record.temperature)
            
            # Create data point using the actual timestamp from the device
            point = Point("aranet4_readings") \
                .tag("device", DEVICE_NAME) \
                .tag("location", LOCATION) \
                .tag("mac_address", ARANET_MAC) \
                .field("co2", int(record.co2)) \
                .field("temperature_f", float(temp_f)) \
                .field("humidity", int(record.humidity)) \
                .field("pressure", float(record.pressure)) \
                .field("battery", int(record.battery)) \
                .time(record.date)  # Use the device's timestamp, not current time
            
            points.append(point)
        
        # Write all points in batch
        if points:
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
            logger.info(f"Successfully wrote {len(points)} historical records to InfluxDB")
        
        client.close()
        
    except InfluxDBError as e:
        logger.error(f"InfluxDB error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error writing to InfluxDB: {e}")
        raise

def main():
    """Main recovery function"""
    start_time = time.time()
    
    try:
        logger.info("=" * 60)
        logger.info("Starting Aranet4 historical data recovery...")
        
        if not INFLUX_TOKEN:
            raise ValueError("INFLUXDB_TOKEN environment variable not set")
        
        # Get historical data from device
        records = get_historical_data()
        
        if records:
            # Show date range of recovered data
            oldest = min(records, key=lambda x: x.date)
            newest = max(records, key=lambda x: x.date)
            logger.info(f"Data range: {oldest.date} to {newest.date}")
            
            # Write to InfluxDB
            write_historical_to_influx(records)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Recovery completed successfully in {elapsed_time:.2f}s")
        else:
            logger.warning("No historical data found on device")
        
    except Exception as e:
        logger.error(f"Recovery failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)