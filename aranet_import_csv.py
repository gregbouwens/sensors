#!/usr/bin/env python3
import os
import csv
import datetime
import logging
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/greg/repos/aranet4/aranet_import.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# InfluxDB Configuration
INFLUX_URL = "http://docker20.dbmob.nl:8086"
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = "homelab"
INFLUX_BUCKET = "aranet4"

# CSV file path (copy your file to the Pi)
CSV_PATH = "/home/greg/repos/aranet4/history.csv"

# Tags
DEVICE_NAME = "aranet4_0B201"
LOCATION = "office"
MAC_ADDRESS = "DF:C1:53:75:BA:4E"

def validate_env():
    if not INFLUX_TOKEN:
        raise ValueError("INFLUXDB_TOKEN not set")
    if not os.path.isfile(CSV_PATH):
        raise FileNotFoundError(f"{CSV_PATH} not found")

def parse_timestamp(ts_str):
    # Example: "06/09/2025 10:17:38 AM"
    return datetime.datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")

def import_csv():
    validate_env()
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    with open(CSV_PATH, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        points = []
        for row in reader:
            try:
                timestamp = parse_timestamp(row["Time(MM/DD/YYYY h:mm:ss A)"])
                co2 = int(row["Carbon dioxide(ppm)"])
                temp_f = float(row["Temperature(°F)"])
                humidity = int(row["Relative humidity(%)"])
                pressure_atm = float(row["Atmospheric pressure(atm)"])
                # Convert atm to hPa
                pressure_hpa = pressure_atm * 1013.25

                point = (
                    Point("aranet4_readings")
                      .tag("device", DEVICE_NAME)
                      .tag("location", LOCATION)
                      .tag("mac_address", MAC_ADDRESS)
                      .field("co2", co2)
                      .field("temperature_f", temp_f)
                      .field("humidity", humidity)
                      .field("pressure", pressure_hpa)
                      .time(timestamp)
                )
                points.append(point)
            except Exception as e:
                logger.error(f"Skipping row due to parse error: {e} -- {row}")
        if not points:
            logger.warning("No points to write")
            return

        try:
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
            logger.info(f"Wrote {len(points)} historical points to InfluxDB")
        except InfluxDBError as e:
            logger.error(f"InfluxDB write failed: {e}")
        finally:
            client.close()

if __name__ == "__main__":
    import_csv()
