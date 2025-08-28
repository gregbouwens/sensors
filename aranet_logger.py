#!/usr/bin/env python3
import aranet4, os
import datetime
import logging
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/greg/repos/sensors/aranet_logger.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# InfluxDB Configuration
INFLUX_URL = "http://docker20.dbmob.nl:8086"
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = "homelab"
INFLUX_BUCKET = "aranet4"

# Aranet4 Configuration
ARANET_MAC = "DF:C1:53:75:BA:4E"
DEVICE_NAME = "aranet4_0B201"
LOCATION = "office"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit"""
    return celsius * 9.0 / 5.0 + 32.0

def validate_environment():
    """Validate required environment variables and configuration"""
    if not INFLUX_TOKEN:
        raise ValueError("INFLUXDB_TOKEN environment variable not set")
    
    if not ARANET_MAC:
        raise ValueError("ARANET_MAC not configured")
    
    logger.info("Environment validation passed")

def get_aranet_readings_with_retry():
    """Get Aranet4 readings with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Attempting to read from Aranet4 (attempt {attempt + 1}/{MAX_RETRIES})")
            current = aranet4.client.get_current_readings(ARANET_MAC)
            
            # Validate readings (using Celsius for validation)
            if current.co2 <= 0 or current.temperature < -50 or current.temperature > 80:
                raise ValueError(f"Invalid sensor readings: CO2={current.co2}, Temp={current.temperature}")
            
            logger.info(f"Successfully read from Aranet4: CO2={current.co2}ppm")
            return current
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed")
                raise

def write_to_influx_with_retry(current, temp_f):
    """Write data to InfluxDB with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Attempting to write to InfluxDB (attempt {attempt + 1}/{MAX_RETRIES})")
            
            # Create InfluxDB client
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            write_api = client.write_api(write_options=SYNCHRONOUS)
            
            # Create data point with proper typing
            point = Point("aranet4_readings") \
                .tag("device", DEVICE_NAME) \
                .tag("location", LOCATION) \
                .tag("mac_address", ARANET_MAC) \
                .field("co2", int(current.co2)) \
                .field("temperature_f", float(temp_f)) \
                .field("humidity", int(current.humidity)) \
                .field("pressure", float(current.pressure)) \
                .field("battery", int(current.battery)) \
                .time(datetime.datetime.utcnow())
            
            # Write to InfluxDB
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
            
            logger.info("Successfully wrote to InfluxDB")
            client.close()
            return
            
        except InfluxDBError as e:
            logger.warning(f"InfluxDB attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {MAX_RETRIES} InfluxDB attempts failed")
                raise
        except Exception as e:
            logger.error(f"Unexpected error writing to InfluxDB: {e}")
            raise
        finally:
            try:
                client.close()
            except:
                pass

def log_aranet_data():
    """Main function to collect and log Aranet4 data"""
    start_time = time.time()
    
    try:
        logger.info("=" * 50)
        logger.info("Starting Aranet4 data collection...")
        
        # Validate environment
        validate_environment()
        
        # Get sensor readings
        current = get_aranet_readings_with_retry()
        
        # Convert temperature to Fahrenheit
        temp_c = current.temperature
        temp_f = c_to_f(temp_c)
        
        # Write to InfluxDB
        write_to_influx_with_retry(current, temp_f)
        
        # Success message
        elapsed_time = time.time() - start_time
        logger.info(f"Successfully logged: CO2={current.co2}ppm, Temp={temp_f:.1f}°F, Humidity={current.humidity}%, Pressure={current.pressure}hPa, Battery={current.battery}% (took {elapsed_time:.2f}s)")
        
    except Exception as e:
        logger.error(f"Failed to log data: {e}")
        return 1  # Exit code for cron monitoring
    
    return 0

if __name__ == "__main__":
    exit_code = log_aranet_data()
    exit(exit_code)
