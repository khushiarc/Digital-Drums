import streamlit as st
import serial
import serial.tools.list_ports
import time
from PIL import Image, ImageDraw
from io import BytesIO
import pygame
from dataclasses import dataclass
import numpy as np
import math
from typing import Dict, Tuple, List
import threading
import sys
from collections import deque
from datetime import datetime, timedelta

@dataclass
class DrumHit:
    drum_name: str
    velocity: float
    timestamp: datetime

@dataclass
class DrumPosition:
    x: float  # Left-right position in cm
    y: float  # Front-back position in cm

class DrumSoundSystem:
    def __init__(self):
        # Initialize Pygame mixer with widely supported settings
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        except pygame.error as e:
            print(f"Failed to initialize pygame mixer: {e}")
            sys.exit(1)

        # Define drum positions in 3D space (x, y, z in cm)
        self.drum_positions: Dict[str, DrumPosition] = {
            "Kick": DrumPosition(0, 50),      # Center, front
            "Snare": DrumPosition(-20, 30),   # Left, middle
            "Hi-Hat": DrumPosition(-40, 30),  # Far left
            "Crash": DrumPosition(-30, 20),   # Left, high
            "Tom1": DrumPosition(-10, 20),    # Center-left
            "Tom2": DrumPosition(10, 20),     # Center-right
            "Tom3": DrumPosition(30, 30),     # Right
            "Ride": DrumPosition(40, 20)      # Far right
        }

        # Sound dictionary with velocity layers
        self.sounds: Dict[str, Dict[str, pygame.mixer.Sound]] = {}
        
        # Load sound files with velocity layers
        velocities = ['soft', 'medium', 'hard']
        for drum_name, position in self.drum_positions.items():
            self.sounds[drum_name] = {}
            for velocity in velocities:
                try:
                    file_path = f"drum_sounds/{drum_name.lower()}_{velocity}.mp3"
                    self.sounds[drum_name][velocity] = pygame.mixer.Sound(file_path)
                except pygame.error:
                    try:
                        file_path = f"drum_sounds/{drum_name.lower()}.wav"
                        self.sounds[drum_name][velocity] = pygame.mixer.Sound(file_path)
                    except pygame.error as e:
                        print(f"Warning: Could not load sound file for {drum_name}: {e}")

        # Initialize reverb settings
        self.room_size = (300, 400, 250)  # room dimensions in cm
        self.listener_position = (0, 0, 170)  # listener position (head height)

    def calculate_spatial_parameters(self, drum_name: str, velocity: float) -> Tuple[float, float, float]:
        """Calculate volume, panning, and reverb based on drum position and hit velocity"""
        drum_pos = self.drum_positions[drum_name]
        
        dx = drum_pos.x - self.listener_position[0]
        distance = math.sqrt(dx*dx)
        
        max_distance = 200
        distance_factor = max(0, 1 - (distance / max_distance))
        volume = min(1.0, velocity * distance_factor)
        
        panning = max(-1.0, min(1.0, drum_pos.x / 100.0))
        
        room_center_dist = math.sqrt(
            (drum_pos.x / self.room_size[0])**2)
        reverb_amount = min(1.0, room_center_dist * (distance / max_distance))
        
        return volume, panning, reverb_amount

    def apply_spatial_effects(self, sound: pygame.mixer.Sound, volume: float, panning: float, reverb: float) -> pygame.mixer.Sound:
        """Apply spatial audio effects to the sound"""
        try:
            channels = pygame.sndarray.array(sound)
            if len(channels.shape) == 2:
                left_vol = min(1.0, 1.0 - max(0, panning))
                right_vol = min(1.0, 1.0 + max(0, panning))
                channels[:, 0] = channels[:, 0] * left_vol
                channels[:, 1] = channels[:, 1] * right_vol
                
                if reverb > 0:
                    delay_ms = int(30 * reverb)
                    delay_samples = int(delay_ms * 44100 / 1000)
                    reverb_channels = np.roll(channels, delay_samples, axis=0) * reverb * 0.3
                    channels = channels + reverb_channels
                
                channels = np.clip(channels * volume, -32768, 32767)
                return pygame.sndarray.make_sound(channels.astype(np.int16))
            return sound
        except Exception as e:
            print(f"Warning: Could not apply spatial effects: {e}")
            sound.set_volume(volume)
            return sound

    def get_velocity_layer(self, velocity: float) -> str:
        """Determine which velocity layer to use based on hit strength"""
        if velocity < 0.15:
            return 'soft'
        elif velocity < 0.21:
            return 'medium'
        return 'hard'

    def play_sound(self, drum_name: str, velocity: float = 0.7):
        """Play a drum sound with spatial audio effects"""
        if drum_name in self.sounds:
            try:
                velocity_layer = self.get_velocity_layer(velocity)
                base_sound = self.sounds[drum_name][velocity_layer]
                
                volume, panning, reverb = self.calculate_spatial_parameters(drum_name, velocity)
                spatialized_sound = self.apply_spatial_effects(base_sound, volume, panning, reverb)
                spatialized_sound.play()
                
            except pygame.error as e:
                print(f"Error playing sound {drum_name}: {e}")
        else:
            print(f"Warning: Unknown drum sound '{drum_name}'")

class DrumKitGUI:
    def __init__(self):
        self.serial_port = None
        self.baud_rate = 115200
        self.connected = False
        self.setup_complete = False
        self.last_hit = None
        
        # Initialize sound system
        self.sound_system = DrumSoundSystem()
        
        # Drum configuration
        self.LEFT_DRUMS = ["Kick", "Snare", "Hi-Hat", "Crash"]
        self.RIGHT_DRUMS = ["Tom1", "Tom2", "Tom3", "Ride"]
        self.drum_positions = {"Left": {}, "Right": {}}
        
        # Store recent hits with timestamps
        self.recent_hits = deque(maxlen=10)

    def connect_to_port(self, port_name):
        """Attempt to connect to the specified serial port"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            
            self.serial_port = serial.Serial(port_name, self.baud_rate, timeout=0.1)
            self.connected = True
            return True
        except serial.SerialException as e:
            st.error(f"Failed to connect to {port_name}: {e}")
            self.connected = False
            return False
        
    def read_serial_data(self):
        """Read and parse serial data"""
        if not self.connected or not self.serial_port:
            return None
        
        try:
            if self.serial_port.in_waiting:
                line = self.serial_port.readline().decode('utf-8').strip()
                return line
        except Exception as e:
            st.error(f"Error reading serial data: {e}")
            return None

    def disconnect_port(self):
        """Disconnect from the current serial port"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.connected = False
            return True
        except serial.SerialException as e:
            st.error(f"Failed to disconnect: {e}")
            return False
        
    def create_drum_visualization(self, hit_drum=None):
        """Create a visual representation of the drum kit"""
        width, height = 800, 400
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)

        draw.text((350, 30), "Drum Kit Status", fill='black')

        drums = {
            "Left": {
                "Kick": (200, 300),
                "Snare": (300, 200),
                "Hi-Hat": (100, 150),
                "Crash": (50, 100)
            },
            "Right": {
                "Tom1": (400, 150),
                "Tom2": (500, 150),
                "Tom3": (600, 150),
                "Ride": (700, 100)
            }
        }

        for side, side_drums in drums.items():
            for drum_name, pos in side_drums.items():
                if drum_name == hit_drum:
                    color = 'red'
                elif drum_name in self.drum_positions[side]:
                    color = 'green'
                else:
                    color = 'lightgray'

                draw.ellipse([pos[0] - 30, pos[1] - 30, pos[0] + 30, pos[1] + 30],
                            outline='black', fill=color)
                draw.text((pos[0] - 20, pos[1] - 10), drum_name, fill='black')

        buf = BytesIO()
        image.save(buf, format='PNG')
        return buf.getvalue()

    def process_drum_hit(self, data: str):
        """Process drum hit data and play corresponding sound"""
        try:
            parts = data.split(',')
            if len(parts) >= 2:
                drum_name = parts[0]
                velocity = float(parts[1])
                self.last_hit = drum_name
                
                # Add hit to recent hits with timestamp
                self.recent_hits.append(DrumHit(
                    drum_name=drum_name,
                    velocity=velocity,
                    timestamp=datetime.now()
                ))
                
                # Play the sound using the sound system
                self.sound_system.play_sound(drum_name, velocity)
                return drum_name, velocity
        except Exception as e:
            print(f"Error processing drum hit: {e}")
        return None, None

    def get_active_hits(self) -> List[DrumHit]:
        """Return list of hits that occurred within the last 2 seconds"""
        current_time = datetime.now()
        return [hit for hit in self.recent_hits 
                if current_time - hit.timestamp < timedelta(seconds=2)]

    # [Other existing methods remain unchanged]

def init_session_state():
    """Initialize session state variables"""
    if 'drum_kit' not in st.session_state:
        st.session_state.drum_kit = DrumKitGUI()
    if 'setup_mode' not in st.session_state:
        st.session_state.setup_mode = True
    if 'serial_output' not in st.session_state:
        st.session_state.serial_output = []

def main():
    st.set_page_config(page_title="Electronic Drum Kit", layout="wide")
    init_session_state()
    
    with st.sidebar:
        st.header("Controls")
        
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        if not available_ports:
            st.warning("No COM ports detected")
        else:
            selected_port = st.selectbox("Select COM Port", options=available_ports)
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Connect"):
                    if st.session_state.drum_kit.connect_to_port(selected_port):
                        st.success(f"Connected to {selected_port}")
                        st.session_state.setup_mode = True
            
            with col2:
                if st.button("Disconnect"):
                    if st.session_state.drum_kit.disconnect_port():
                        st.success("Disconnected successfully")
                        st.session_state.setup_mode = True
                    
        if st.session_state.drum_kit.connected:
            if st.button("Toggle Setup/Play Mode"):
                st.session_state.setup_mode = not st.session_state.setup_mode
                if not st.session_state.setup_mode:
                    st.session_state.drum_kit.setup_complete = True
            
            if st.button("Clear Serial Output"):
                st.session_state.serial_output = []
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.image(
            st.session_state.drum_kit.create_drum_visualization(
                st.session_state.drum_kit.last_hit
            ),
            use_column_width=True
        )
    
    with col2:
        if st.session_state.drum_kit.connected:
            st.header("Serial Output" if st.session_state.setup_mode else "Drum Hits")
            
            if st.session_state.setup_mode:
                serial_display = st.empty()
                data = st.session_state.drum_kit.read_serial_data()
                if data and data.strip():
                    st.session_state.serial_output.append(data)
                serial_display.text("\n".join(st.session_state.serial_output))
            else:
                # Create containers for hits
                hit_containers = [st.empty() for _ in range(10)]
                
                data = st.session_state.drum_kit.read_serial_data()
                if data and data.strip():
                    drum_name, velocity = st.session_state.drum_kit.process_drum_hit(data)
                
                # Display active hits
                active_hits = st.session_state.drum_kit.get_active_hits()
                for i, container in enumerate(hit_containers):
                    if i < len(active_hits):
                        hit = active_hits[i]
                        container.success(
                            f"Hit detected!\nDrum: {hit.drum_name}\n"
                            f"Velocity: {hit.velocity:.2f}\n"
                            f"Time: {hit.timestamp.strftime('%H:%M:%S.%f')[:-4]}"
                        )
                    else:
                        container.empty()
            
            time.sleep(0.1)
            st.rerun()

if __name__ == "__main__":
    main()
