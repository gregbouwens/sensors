# Eve Room Integration Project Documentation

## Project Status: Awaiting HomeKit Controller for Home Assistant

**Date:** August 28, 2025  
**Current Status:** Direct BLE integration failed due to HomeKit encryption. Awaiting HomeKit Controller hardware for Home Assistant integration.

---

## 🔍 Discovery & Analysis Results

### Device Information
- **Device Name:** Eve Room 1C22
- **Model:** Eve Room 20EBX9901 (Eve Systems)
- **MAC Address:** C9:1F:4A:63:8E:54
- **Protocol:** Apple HomeKit over Bluetooth LE
- **Sensors:** Temperature, Humidity, VOC (Volatile Organic Compounds)

### Technical Findings

#### BLE Services Discovered
```
- Generic Attribute Profile (00001801-0000-1000-8000-00805f9b34fb)
- Multiple HomeKit Services (UUID pattern: 0000XXXX-0000-1000-8000-0026bb765291)
- Eve Custom Service (e863f007-079e-48ff-8f27-9c2605a29f52)
```

#### Why Direct BLE Access Failed
1. **HomeKit Security Model**
   - All characteristics require HomeKit pairing before reading
   - ATT error 0x0e (Unlikely Error) = Authentication required
   - Encrypted communication using SRP (Secure Remote Password) protocol

2. **Advertisement Data Analysis**
   - Static manufacturer data: `06310058d5768b76ac0a00500f0202ec408f3a`
   - No sensor data in advertisements (unlike simpler BLE sensors)
   - Data remains constant across multiple scans

3. **Connection Attempts**
   - Successfully connected to device
   - Service discovery completed
   - All read attempts failed without HomeKit pairing
   - Error: "Service Discovery has not been performed yet" (misleading - actually auth required)

---

## ✅ Recommended Solution: Home Assistant with HomeKit Controller

### Architecture Overview
```
Eve Room 1C22 
    ↓ (HomeKit BLE)
Home Assistant + HomeKit Controller
    ↓ (REST API / MQTT)
Python Script (eve_logger.py)
    ↓ (HTTP API)
InfluxDB
```

### Prerequisites
- [ ] Home Assistant installation (✓ Already running)
- [ ] HomeKit Controller integration for Home Assistant
- [ ] Eve Room unpaired from iPhone (to allow HA pairing)
- [ ] Eve Room PIN code (check device or manual)

### Implementation Plan

#### Phase 1: Home Assistant Setup
1. **Install HomeKit Controller Integration**
   ```yaml
   # configuration.yaml
   homekit_controller:
   ```

2. **Pair Eve Room with Home Assistant**
   - Remove Eve Room from Apple Home app
   - In HA: Settings → Devices & Services → Add Integration → HomeKit Controller
   - Enter PIN when prompted
   - Verify sensors appear: temperature, humidity, VOC

3. **Configure HA Sensor Entities**
   - Note entity IDs (likely: `sensor.eve_room_1c22_temperature`, etc.)
   - Set up history retention if needed

#### Phase 2: Data Export Script

4. **Create eve_logger.py**
   ```python
   #!/usr/bin/env python3
   """
   Eve Room Data Logger via Home Assistant
   Fetches sensor data from HA and logs to InfluxDB
   """
   
   import requests
   import os
   from influxdb_client import InfluxDBClient, Point
   from dotenv import load_dotenv
   import logging
   
   # Home Assistant Configuration
   HA_URL = "http://homeassistant.local:8123"
   HA_TOKEN = os.environ.get("HA_TOKEN")  # Long-lived access token
   
   # Sensor entity IDs (update after pairing)
   EVE_TEMP_ENTITY = "sensor.eve_room_1c22_temperature"
   EVE_HUMIDITY_ENTITY = "sensor.eve_room_1c22_humidity"
   EVE_VOC_ENTITY = "sensor.eve_room_1c22_voc"
   ```

5. **Test Data Flow**
   - Verify HA API access
   - Confirm sensor readings
   - Test InfluxDB writes

6. **Add to Cron**
   ```bash
   */5 * * * * /bin/bash -lc 'cd $HOME/repos/sensors && source sensors_env/bin/activate && python3 eve_logger.py >> $HOME/repos/sensors/cron.log 2>&1'
   ```

---

## 📝 Environment Configuration

### Current .env Variables
```bash
# InfluxDB
INFLUX_URL=<configured>
INFLUXDB_TOKEN=<configured>
INFLUX_ORG=<configured>
INFLUX_BUCKET=<configured>

# Aranet4 (working)
ARANET_MAC=DF:C1:53:75:BA:4E
DEVICE_NAME=<configured>
LOCATION=<configured>

# To be added for Eve Room:
HA_TOKEN=<generate from HA>
EVE_DEVICE_NAME=Eve_Room_1C22
```

### Home Assistant Long-Lived Token
1. Go to HA → User Profile → Security
2. Create Long-lived access token
3. Save to .env file

---

## 🔧 Alternative Approaches Considered

### ❌ Direct BLE (Failed)
- Blocked by HomeKit encryption
- No public protocol documentation
- Would require reverse engineering HomeKit

### ❌ Python HomeKit Library
- Libraries exist (HAP-python, pyHomeKit)
- Complex implementation
- Easier to use existing Home Assistant integration

### ❌ Bluetooth Sniffing
- Could capture iPhone ↔ Eve communication
- Encrypted payload, would need keys
- Not practical for production use

---

## 📊 Current Sensor Setup

### Working Sensors
| Sensor | Script | Data Points | Frequency |
|--------|--------|-------------|-----------|
| Aranet4 | aranet_logger.py | CO2, Temp, Humidity, Pressure, Battery | Every 5 min |
| Eve Room | *Pending HA integration* | Temp, Humidity, VOC | TBD |

### InfluxDB Schema
```
Measurement: aranet4_readings
Tags: device, location, mac_address
Fields: co2, temperature_f, humidity, pressure, battery

Measurement: eve_room_readings (proposed)
Tags: device, location, source
Fields: temperature_f, humidity, voc_ppb
```

---

## 🚀 Next Steps (When HomeKit Controller Available)

1. **Unpair Eve Room from iPhone**
   - Open Home app
   - Remove Eve Room accessory
   - Factory reset if needed (check manual)

2. **Set up HomeKit Controller in HA**
   - Install integration
   - Pair with Eve Room
   - Note entity IDs

3. **Implement eve_logger.py**
   - Use template above
   - Add HA API calls
   - Test InfluxDB writes

4. **Update Cron Job**
   - Add eve_logger.py to rotation
   - Consider combining scripts if desired

5. **Verify Data Flow**
   - Check InfluxDB for new measurements
   - Set up Grafana dashboards
   - Monitor for reliability

---

## 📚 Resources

- [Home Assistant HomeKit Controller Docs](https://www.home-assistant.io/integrations/homekit_controller/)
- [HA REST API Documentation](https://developers.home-assistant.io/docs/api/rest/)
- [Eve Room Specifications](https://www.evehome.com/en-us/eve-room)
- [Project Repository](/home/greg/repos/sensors)

---

## 🔍 Troubleshooting Notes

### If Pairing Fails
- Ensure Eve Room is reset and unpaired from all devices
- Check PIN code (usually on device or in manual)
- Verify Bluetooth is enabled on HA host
- May need to move HA host closer during pairing

### If No VOC Readings
- Eve Room may need calibration time (24-48 hours)
- VOC sensor might not be exposed via HomeKit (check HA entities)
- Consider using Eve app briefly to verify sensor is working

### Cron Job Issues
- Already resolved pytz import issue
- Virtual environment activation working
- Logs in /home/greg/repos/sensors/cron.log

---

*Document prepared for resuming integration once HomeKit Controller hardware is available.*