# Open bluetooth control
sudo bluetoothctl

# Turn on scanning
scan on

# Look for your Aranet4 device (should appear as "Aranet4 XXXXX")
# Note down the MAC address (format: XX:XX:XX:XX:XX:XX)

# Once you see it, stop scanning
scan off

# Pair with your device
pair XX:XX:XX:XX:XX:XX

# Trust the device for future connections
trust XX:XX:XX:XX:XX:XX

# Exit bluetoothctl
exit

## InfluxDB
pip3 install 'influxdb-client[ciso]'