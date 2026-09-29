import os
from machine import Pin, time_pulse_us, I2C
import time
import math
from statistics import mode
from mpu6050 import MPU6050

class DrumSystem:
    def __init__(self):
        # Configuration file path
        self.CONFIG_FILE = "drum_layout.txt"
        
        # Pin Definitions
        self.TRIG_PIN_X_LEFT = 5    # Left X sensor
        self.ECHO_PIN_X_LEFT = 18
        self.TRIG_PIN_X_RIGHT = 12  # Right X sensor
        self.ECHO_PIN_X_RIGHT = 13
        self.BUTTON_PIN = 19
        
        # Constants
        self.COOLDOWN_PERIOD = 0.2
        self.ACCELERATION_THRESHOLD = 2.0
        self.READING_COUNT = 3
        self.DETECTION_MARGIN = 5  # Detection margin in cm
        self.MAX_DETECTION_DISTANCE = 200  # Maximum valid distance reading in cm
        
        # Drum configuration
        self.DRUMS = ["Kick", "Snare", "Tom1", "Tom2", "Ride", "Hi-Hat", "Crash", "Tom3"]
        
        # Initialize system
        self.initialize_system()
        
    def initialize_system(self):
        """Initialize all system components"""
        # I2C Setup
        self.i2c_left = I2C(0, scl=Pin(22), sda=Pin(21))
        self.i2c_right = I2C(1, scl=Pin(26), sda=Pin(25))
        
        # Initialize MPU sensors
        self.mpu_left = MPU6050(self.i2c_left)
        self.mpu_right = MPU6050(self.i2c_right)
        
        # Initialize pins
        self.trig_x_left = Pin(self.TRIG_PIN_X_LEFT, Pin.OUT)
        self.echo_x_left = Pin(self.ECHO_PIN_X_LEFT, Pin.IN)
        self.trig_x_right = Pin(self.TRIG_PIN_X_RIGHT, Pin.OUT)
        self.echo_x_right = Pin(self.ECHO_PIN_X_RIGHT, Pin.IN)
        self.button = Pin(self.BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        
        # Initialize state variables
        self.drum_positions = []
        self.last_hit_time = 0
        
    def calculate_velocity(self, total_acceleration):
        """Calculate normalized velocity from acceleration"""
        velocity = (total_acceleration - self.ACCELERATION_THRESHOLD) / (16.0 - self.ACCELERATION_THRESHOLD)
        return max(0.1, min(1.0, velocity))
        
    def measure_distance(self, trig, echo):
        """Measure distance using specified ultrasonic sensor"""
        trig.value(0)
        time.sleep_us(2)
        trig.value(1)
        time.sleep_us(10)
        trig.value(0)
        pulse_duration = time_pulse_us(echo, 1)
        distance = (pulse_duration / 58)
        return min(distance, self.MAX_DETECTION_DISTANCE)
        
    def get_stable_distance(self, trig, echo):
        """Get stable distance reading from specified sensor"""
        distances = [math.floor(self.measure_distance(trig, echo)) for _ in range(5)]
        try:
            return mode(distances)
        except:
            return distances[0]
            
    def detect_hit(self, mpu):
        """Detect hit using specified MPU6050"""
        hit_detected = 0
        max_acceleration = 0
        
        for _ in range(self.READING_COUNT):
            values = mpu.get_accel()
            ax = values["AcX"] / 8192.0
            ay = values["AcY"] / 8192.0
            az = values["AcZ"] / 8192.0
            total_acceleration = math.sqrt(ax*ax + ay*ay + az*az)
            
            if total_acceleration > self.ACCELERATION_THRESHOLD and az < -1.0:
                hit_detected += 1
                max_acceleration = max(max_acceleration, total_acceleration)
            
            time.sleep_us(500)
        
        if hit_detected >= (self.READING_COUNT // 2 + 1):
            return True, max_acceleration
        return False, 0
        
    def is_position_valid(self, new_x1, new_x2):
        """Check if new position is valid"""
        if (new_x1 >= self.MAX_DETECTION_DISTANCE or 
            new_x2 >= self.MAX_DETECTION_DISTANCE):
            return False
        
        for x1, x2 in self.drum_positions:
            if (abs(new_x1 - x1) < self.DETECTION_MARGIN and 
                abs(new_x2 - x2) < self.DETECTION_MARGIN):
                return False
        return True
        
    def save_drum_layout(self):
        """Save drum layout to file"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                for x1, x2 in self.drum_positions:
                    f.write(f"{x1},{x2}\n")
            print("Drum layout saved successfully!")
        except Exception as e:
            print(f"Error saving drum layout: {e}")
            
    def load_drum_layout(self):
        """Load drum layout from file"""
        try:
            if self.CONFIG_FILE not in os.listdir():
                return False
            
            loaded_positions = []
            with open(self.CONFIG_FILE, 'r') as f:
                for line in f:
                    x1, x2= map(float, line.strip().split(','))
                    loaded_positions.append((x1, x2))
            
            if len(loaded_positions) == len(self.DRUMS):
                self.drum_positions = loaded_positions
                return True
            return False
        except Exception as e:
            print(f"Error loading drum layout: {e}")
            return False
            
    def setup_drums(self):
        """Setup drums in 2D space"""
        print("Setting up drums in 2D space...")
        print("Press the button to add each drum position")
        
        self.drum_positions = []
        while len(self.drum_positions) < len(self.DRUMS):
            if not self.button.value():
                time.sleep(0.1)  # Debounce
                if not self.button.value():
                    current_drum = self.DRUMS[len(self.drum_positions)]
                    print(f"Measuring position for {current_drum}")
                    
                    x1_distance = self.get_stable_distance(self.trig_x_left, self.echo_x_left)
                    x2_distance = self.get_stable_distance(self.trig_x_right, self.echo_x_right)
                    
                    if self.is_position_valid(x1_distance, x2_distance):
                        self.drum_positions.append((x1_distance, x2_distance))
                        print(f"{current_drum} position set at (L:{x1_distance}cm, R:{x2_distance}cm)")
                    else:
                        if (x1_distance >= self.MAX_DETECTION_DISTANCE or 
                            x2_distance >= self.MAX_DETECTION_DISTANCE):
                            print("Position too far. Move closer and try again.")
                        else:
                            print("Position too close to existing drum. Try again.")
                    
                    time.sleep(1)
            time.sleep(0.1)
        
        print("Drum setup complete!")
        self.save_drum_layout()
        
    def identify_drum(self, x_distance, is_left_hit):
        """Identify which drum was hit"""        
        for i, (x1, x2) in enumerate(self.drum_positions):
            reference_x = x1 if is_left_hit else x2
            detected_x = x_distance
            
            if ((reference_x - self.DETECTION_MARGIN) <= detected_x <= (reference_x + self.DETECTION_MARGIN)):
                return self.DRUMS[i], math.sqrt((detected_x - reference_x)**2)
        
        return None, None
        
    def run(self):
        """Main run loop"""
        print("2D Digital Drums system starting...")
        print("\nAvailable drums:")
        for drum in self.DRUMS:
            print(f"- {drum}")
        
        # Load or setup drum configuration
        if self.load_drum_layout():
            print("\nPrevious drum layout found.")
            print("Press button within 5 seconds to reconfigure...")
            
            start_time = time.time()
            while time.time() - start_time < 5:
                if not self.button.value():
                    time.sleep(0.1)
                    if not self.button.value():
                        print("Reconfiguring drums...")
                        self.setup_drums()
                        break
                time.sleep(0.1)
            else:
                print("Using existing drum layout.")
        else:
            print("\nNo previous configuration found.")
            self.setup_drums()
        
        print("\nStarting drum detection...")
        print("System ready!")
        
        while True:
            current_time = time.time()
            
            if current_time - self.last_hit_time >= self.COOLDOWN_PERIOD:
                left_hit, left_accel = self.detect_hit(self.mpu_left)
                right_hit, right_accel = self.detect_hit(self.mpu_right)
                
                if left_hit or right_hit:

                    if left_hit:
                        x_distance = self.get_stable_distance(self.trig_x_left, self.echo_x_left)
                    else:
                        x_distance = self.get_stable_distance(self.trig_x_right, self.echo_x_right)
                    
                    drum_name, actual_distance = self.identify_drum(x_distance, left_hit)
                    
                    if drum_name:
                        velocity = self.calculate_velocity(left_accel if left_hit else right_accel)
                        print(f"{drum_name},{velocity:.2f},{actual_distance:.1f}")
                    
                    self.last_hit_time = current_time
            
            time.sleep_us(100)

def main():
    drum_system = DrumSystem()
    try:
        drum_system.run()
    except KeyboardInterrupt:
        print("\nProgram stopped by user")
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == '__main__':
    main()
