#!/usr/bin/env python3
import aranet4, os
import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# InfluxDB Configuration
INFLUX_URL = "http://docker20.dbmob.nl:8086"
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN")
INFLUX_ORG = "homelab"
INFLUX_BUCKET = "aranet4"

# Aranet4 Configuration
ARANET_MAC = "DF:C1:53:75:BA:4E"

def log_aranet_data():
    try:
        # Get current readings from Aranet4
        current = aranet4.client.get_current_readings(ARANET_MAC)
        
        # Create InfluxDB client
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Create data point
        point = Point("aranet4_readings") \
            .tag("device", "aranet4") \
            .tag("location", "office") \
            .field("co2", current.co2) \
            .field("temperature", current.temperature) \
            .field("humidity", current.humidity) \
            .field("pressure", current.pressure) \
            .field("battery", current.battery) \
            .time(datetime.datetime.utcnow())
        
        # Write to InfluxDB
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        
        print(f"Successfully logged: CO2={current.co2}ppm, Temp={current.temperature}°C, Humidity={current.humidity}%, Pressure={current.pressure}hPa, Battery={current.battery}%")
        
        # Close client
        client.close()
        
    except Exception as e:
        print(f"Error logging data: {e}")

if __name__ == "__main__":
    log_aranet_data()
