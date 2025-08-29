#!/usr/bin/env python3
"""
Eve Room Advertisement Scanner
Monitors BLE advertisements from Eve Room for sensor data
"""

import asyncio
import struct
from bleak import BleakScanner
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVE_MAC = "C9:1F:4A:63:8E:54"

def parse_eve_advertisement(manufacturer_data):
    """
    Try to parse Eve Room advertisement data
    Based on HomeKit and Eve's custom format
    """
    parsed = {}
    
    # Apple manufacturer ID is 0x004C
    if 0x004C in manufacturer_data:
        data = manufacturer_data[0x004C]
        logger.info(f"Raw Apple data: {data.hex()}")
        
        # Try to parse based on common patterns
        # Eve devices often encode sensor data in the manufacturer data
        if len(data) >= 16:
            # Different offsets might contain different data
            # This is experimental - we'll need to observe patterns
            
            # Try various interpretations
            if len(data) >= 4:
                # Try reading as uint16 values at different offsets
                for i in range(0, min(len(data)-1, 16), 2):
                    try:
                        val = struct.unpack('<H', data[i:i+2])[0]
                        logger.info(f"  Offset {i}: uint16 = {val} (0x{val:04x})")
                    except:
                        pass
            
            # Look for temperature/humidity patterns
            # Temperature is often in 0.01°C units
            # Humidity is often in 0.01% units
            if len(data) >= 8:
                try:
                    # Common pattern: bytes 6-7 might be temperature
                    # bytes 8-9 might be humidity
                    temp_raw = struct.unpack('<h', data[6:8])[0]
                    humi_raw = struct.unpack('<H', data[8:10])[0]
                    
                    # Convert to reasonable values
                    temp_c = temp_raw / 100.0
                    humidity = humi_raw / 100.0
                    
                    # Sanity check
                    if -40 <= temp_c <= 80 and 0 <= humidity <= 100:
                        parsed['temperature_c'] = temp_c
                        parsed['humidity'] = humidity
                        logger.info(f"  Possible temp: {temp_c:.1f}°C, humidity: {humidity:.1f}%")
                except:
                    pass
    
    return parsed

async def monitor_eve_advertisements():
    """
    Continuously monitor Eve Room advertisements
    """
    logger.info("Starting Eve Room advertisement monitor...")
    
    def detection_callback(device, advertisement_data):
        if device.address == EVE_MAC:
            timestamp = datetime.now().isoformat()
            logger.info(f"\n[{timestamp}] Eve Room advertisement:")
            logger.info(f"  Name: {device.name}")
            logger.info(f"  Address: {device.address}")
            
            if advertisement_data.manufacturer_data:
                parsed = parse_eve_advertisement(advertisement_data.manufacturer_data)
                if parsed:
                    logger.info(f"  Parsed data: {parsed}")
            
            # Also show service data if present
            if advertisement_data.service_data:
                logger.info(f"  Service data present:")
                for uuid, data in advertisement_data.service_data.items():
                    logger.info(f"    {uuid}: {data.hex()}")
    
    # Create scanner with callback
    scanner = BleakScanner(detection_callback=detection_callback)
    
    # Start scanning
    await scanner.start()
    
    # Run for 30 seconds to collect multiple advertisements
    await asyncio.sleep(30)
    
    # Stop scanning
    await scanner.stop()
    
    logger.info("Monitoring complete")

async def main():
    """Main function"""
    await monitor_eve_advertisements()

if __name__ == "__main__":
    asyncio.run(main())