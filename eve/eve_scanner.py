#!/usr/bin/env python3
"""
Eve Room BLE Scanner
Discovers and analyzes Eve Room sensor characteristics
"""

import asyncio
import struct
from bleak import BleakScanner, BleakClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVE_MAC = "C9:1F:4A:63:8E:54"

async def scan_for_eve():
    """Scan for Eve Room device and show advertisement data"""
    logger.info("Scanning for Eve Room device...")
    
    devices = await BleakScanner.discover(timeout=10)
    
    for device in devices:
        if device.name and ("Eve" in device.name or device.address == EVE_MAC):
            logger.info(f"Found Eve device: {device.name} ({device.address})")
            
            # Show metadata including manufacturer data
            if hasattr(device, 'metadata') and device.metadata:
                if 'rssi' in device.metadata:
                    logger.info(f"  RSSI: {device.metadata['rssi']}")
                logger.info(f"  Metadata: {device.metadata}")
                
                # Try to parse manufacturer data
                if 'manufacturer_data' in device.metadata:
                    for company_id, data in device.metadata['manufacturer_data'].items():
                        logger.info(f"  Manufacturer ID: {hex(company_id)}")
                        logger.info(f"  Manufacturer Data: {data.hex()}")
                        
                        # Apple company ID is 0x004C
                        if company_id == 0x004C:
                            logger.info("  This is Apple manufacturer data (HomeKit device)")
                            try:
                                # Try to parse the data
                                if len(data) >= 2:
                                    logger.info(f"    Type: {data[0]:02x}")
                                    logger.info(f"    Length: {data[1]:02x}")
                                    if len(data) > 2:
                                        logger.info(f"    Payload: {data[2:].hex()}")
                            except Exception as e:
                                logger.error(f"    Error parsing: {e}")
            
            return device
    
    logger.warning(f"Eve Room device not found at {EVE_MAC}")
    return None

async def discover_services(address):
    """Connect to device and discover all services and characteristics"""
    logger.info(f"\nAttempting to connect to {address}...")
    
    try:
        async with BleakClient(address, timeout=30) as client:
            logger.info(f"Connected: {client.is_connected}")
            
            # Get all services
            services = client.services
            
            logger.info("\nDiscovered Services and Characteristics:")
            for service in services:
                logger.info(f"\nService: {service.uuid}")
                logger.info(f"  Description: {service.description}")
                
                for char in service.characteristics:
                    logger.info(f"  Characteristic: {char.uuid}")
                    logger.info(f"    Properties: {char.properties}")
                    logger.info(f"    Description: {char.description}")
                    
                    # Try to read if readable
                    if "read" in char.properties:
                        try:
                            value = await client.read_gatt_char(char.uuid)
                            logger.info(f"    Value (hex): {value.hex()}")
                            logger.info(f"    Value (raw): {value}")
                            
                            # Try to interpret as string
                            try:
                                text = value.decode('utf-8')
                                logger.info(f"    Value (text): {text}")
                            except:
                                pass
                                
                            # Try to interpret as numbers
                            try:
                                if len(value) == 2:
                                    val = struct.unpack('<H', value)[0]
                                    logger.info(f"    Value (uint16): {val}")
                                elif len(value) == 4:
                                    val = struct.unpack('<f', value)[0]
                                    logger.info(f"    Value (float): {val}")
                            except:
                                pass
                        except Exception as e:
                            logger.info(f"    Could not read: {e}")
                    
                    # Check for descriptors
                    for descriptor in char.descriptors:
                        logger.info(f"    Descriptor: {descriptor}")
                        
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        logger.info("Note: You may need to unpair the device from your iPhone first")
        logger.info("Or the device may require HomeKit pairing")

async def main():
    """Main scanning function"""
    # First scan for the device
    device = await scan_for_eve()
    
    if device:
        # Try to connect and discover services
        await discover_services(device.address)
    else:
        logger.error("Could not find Eve Room device")

if __name__ == "__main__":
    asyncio.run(main())