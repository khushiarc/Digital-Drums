from machine import I2C, Pin
import math
import time

class MPU6050:
    def __init__(self, i2c):
        self.i2c = i2c
        self.addr = 0x68  # MPU6050 I2C address
        self.i2c.writeto_mem(self.addr, 0x6B, b'\x00')  # Wake the sensor
        self.i2c.writeto_mem(self.addr, 0x1C, b'\x08')
        
    def read_raw_data(self, reg):
        high = self.i2c.readfrom_mem(self.addr, reg, 1)
        low = self.i2c.readfrom_mem(self.addr, reg + 1, 1)
        value = (high[0] << 8) | low[0]
        if value > 32768:
            value -= 65536
        return value
        
    def get_values(self):
        # Read accelerometer data
        ax = self.read_raw_data(0x3B)  # X-axis
        ay = self.read_raw_data(0x3D)  # Y-axis
        az = self.read_raw_data(0x3F)  # Z-axis
        return ax, ay, az
        
    def get_accel(self):
        # Get accelerometer values and return as dictionary
        ax, ay, az = self.get_values()
        return {
            "AcX": ax,
            "AcY": ay,
            "AcZ": az
        }
        
    def get_gyro(self):
        # Read gyroscope data
        gx = self.read_raw_data(0x43)  # X-axis
        gy = self.read_raw_data(0x45)  # Y-axis
        gz = self.read_raw_data(0x47)  # Z-axis
        return gx / 131.0, gy / 131.0, gz / 131.0  # Scale factors for ±250°/s