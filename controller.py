import gi
import time
import csv
from datetime import datetime
import hailo
import RPi.GPIO as GPIO
from hailo_apps_infra.hailo_rpi_common import get_caps_from_pad, get_numpy_from_buffer, app_callback_class
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp
from gi.repository import Gst

# GStreamer init
gi.require_version('Gst', '1.0')
Gst.init(None)

# GPIO setup
module1 = [17, 27, 22]
module2 = [23, 24, 25]
module3 = [5, 6, 13]

GPIO.setmode(GPIO.BCM)
for pin in module1:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)  # Initialize OFF
    
for pin in module2:
	GPIO.setup(pin, GPIO.OUT)
	GPIO.output(pin, GPIO.HIGH)

for pin in module3:
	GPIO.setup(pin, GPIO.OUT)
	GPIO.output(pin, GPIO.HIGH)

# Logging setup
CSV_FILE = "/home/just_whiz/hailo-rpi5-examples/basic_pipelines/light_log.csv"
TXT_FILE = "/home/just_whiz/hailo-rpi5-examples/basic_pipelines/light_logtxt"

csv_header = ['Timestamp', 'Light Color', 'State', 'Response Time (s)', 'Time Since Last Change (s)', 'FPS', 'Runtime (s)', 'Detection %', 'Confidences', 'Other Object Counter', 'Other Object Confidence % Average']

# Initialize log files with headers
with open(CSV_FILE, 'w', newline='') as f_csv:
    csv_writer = csv.writer(f_csv)
    csv_writer.writerow(csv_header)

with open(TXT_FILE, 'w') as f_txt:
    f_txt.write(", ".join(csv_header) + "\n")


class user_app_callback_class(app_callback_class):
    """
    Custom callback class for processing Hailo AI detection results and controlling traffic lights.
    
    This class handles:
    - Object detection processing
    - Traffic light control based on detection counts
    - Logging system events to CSV and TXT files
    """
    def __init__(self):
        super().__init__()
        self.target_object = "car"
        
        # Counters for detection statistics
        self.detection_counter = 0
        self.no_detection_counter = 0
        
        # Timing variables
        self.start_time = time.time()
        self.last_change_time = time.time()
        self.total_frames = 0
        self.frames_with_detections = 0
        
        # Detection data
        self.last_confidences = []
        self.detected_objects = {}  # Dictionary to track all detected objects
        self.other_object_count = 0  # Counter for non-car objects
        self.other_object_confidences = []  # List to store confidences of other objects
        
        # Light control
        self.current_light = None
        
        # Light threshold control using lists [min_value, max_value]
        # GREEN: > 10 cars
        # YELLOW: 5-10 cars
        # RED: < 5 cars
        self.GREEN_THRESHOLD = [10, 999]  # More than 10 cars
        self.YELLOW_THRESHOLD = [5, 10]   # Between 5 and 10 cars
        self.RED_THRESHOLD = [0, 4]       # Less than 5 cars
        
        # Enable/disable light control
        self.lights_enabled = True
        
        # Last log time to control log frequency
        self.last_log_time = 0
        self.log_interval = 0.1  # seconds

    def switch_light(self, color):
        """
        Switch the traffic lights to the specified color and log the change.
        
        Args:
            color (str): Color to switch to ('RED', 'YELLOW', 'GREEN', or None for OFF)
        """
        now = time.time()
        
        # Skip if same light is already active or lights are disabled
        if color == self.current_light or not self.lights_enabled:
            return
        
        # Turn off all lights
        for pin in module1, module2, module3:
            GPIO.output(pin, GPIO.HIGH)
        
        # Map colors to GPIO pins
        color_map = {'RED': module1, 'YELLOW': module2, 'GREEN': module3}
        light_group = color_map.get(color)
        
        # Turn on the appropriate light pins
        if light_group and self.lights_enabled:
            for pin in light_group:
                GPIO.output(pin, GPIO.LOW)
        
        # Update current light state
        self.current_light = color
        self.last_change_time = now
        
        # Log the light change with special note
        self.log_status(note="LIGHT CHANGED")

    def log_status(self, note=""):
        """
        Log the current system status to CSV, TXT files and console.
        This function is called for each frame to provide continuous logging.
        
        Args:
            note (str, optional): Additional note for the log entry
        """
        now = time.time()
        response_time = now - self.last_change_time
        runtime = now - self.start_time
        fps = self.total_frames / runtime if runtime > 0 else 0
        detection_rate = (self.frames_with_detections / self.total_frames) * 100 if self.total_frames else 0
        
        # Format all detected objects
        objects_str = " | ".join([f"{obj}: {count}" for obj, count in self.detected_objects.items()])
        
        # Format confidence levels
        confidence_str = ";".join([f"{label}:{conf:.2f}" for label, conf in self.last_confidences])
        
        # Calculate average confidence for other objects
        other_obj_avg_confidence = 0
        if self.other_object_confidences:
            other_obj_avg_confidence = sum(self.other_object_confidences) / len(self.other_object_confidences) * 100
        
        # Create log entry
        row = [
            datetime.now().isoformat(),
            self.current_light if self.current_light else 'OFF',
            'ON' if (self.current_light and self.lights_enabled) else 'OFF',
            f"{response_time:.3f}",
            f"{now - self.last_change_time:.3f}",
            f"{fps:.2f}",
            f"{runtime:.2f}",
            f"{detection_rate:.2f}",
            objects_str,
            confidence_str,
            str(self.other_object_count),
            f"{other_obj_avg_confidence:.2f}"
        ]
        
        # Add note if provided
        if note:
            row.append(f"Note: {note}")
        
        log_entry = ", ".join(row)
        
        # Always print to console for debugging
        print(log_entry)
        
        # Write to log files with proper error handling
        try:
            with open(CSV_FILE, 'a', newline='') as f_csv:
                writer = csv.writer(f_csv)
                writer.writerow(row)
                f_csv.flush()  # Ensure data is written immediately
            
            with open(TXT_FILE, 'a') as f_txt:
                f_txt.write(log_entry + "\n")
                f_txt.flush()  # Ensure data is written immediately
        except Exception as e:
            print(f"Logging failed: {e}")

    def toggle_lights(self, enabled=None):
        """
        Enable or disable all traffic lights.
        
        Args:
            enabled (bool, optional): If True, enable lights; if False, disable lights;
                                      if None, toggle current state
        """
        if enabled is None:
            self.lights_enabled = not self.lights_enabled
        else:
            self.lights_enabled = enabled
        
        # Turn off all lights if disabled
        if not self.lights_enabled:
            for pin in ALL_LIGHTS:
                GPIO.output(pin, GPIO.HIGH)
            print("Lights disabled")
            self.log_status(note="LIGHTS DISABLED")
        else:
            print("Lights enabled")
            self.log_status(note="LIGHTS ENABLED")
            # Restore current light if there is one
            if self.current_light:
                color_map = {'RED': module1, 'YELLOW': module2, 'GREEN': module3}
                light_group = color_map.get(self.current_light)
                if light_group:
                    for pin in light_group:
                        GPIO.output(pin, GPIO.LOW)


def app_callback(pad, info, user_data):
    """
    Callback function for processing detection results from the Hailo AI accelerator.
    
    This function is called for each frame processed by the Hailo AI accelerator.
    It detects objects, controls traffic lights based on car count, and logs results.
    
    Args:
        pad: GStreamer pad
        info: Probe info
        user_data: Custom user data object
        
    Returns:
        Gst.PadProbeReturn.OK: Continue processing
    """
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    user_data.total_frames += 1

    format, width, height = get_caps_from_pad(pad)
    frame = get_numpy_from_buffer(buffer, format, width, height) if user_data.use_frame else None

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Reset object counts
    car_count = 0
    user_data.detected_objects = {}
    user_data.last_confidences = []
    user_data.other_object_count = 0
    user_data.other_object_confidences = []

    # Count all objects by type
    for detection in detections:
        label = detection.get_label()
        confidence = detection.get_confidence()
        
        # Add to detected objects count
        if label in user_data.detected_objects:
            user_data.detected_objects[label] += 1
        else:
            user_data.detected_objects[label] = 1
            
        # Save confidence for logging
        user_data.last_confidences.append((label, confidence))
        
        # Count cars for traffic light control
        if label == user_data.target_object and confidence > 0.4:
            car_count += 1
        # Count other objects separately
        elif label != user_data.target_object:
            user_data.other_object_count += 1
            user_data.other_object_confidences.append(confidence)

    user_data.frames_with_detections += 1 if len(user_data.detected_objects) > 0 else 0

    # Control traffic lights based on car count with new thresholds
    # GREEN: > 10 cars
    # YELLOW: 5-10 cars
    # RED: < 5 cars
    if car_count > user_data.GREEN_THRESHOLD[0]:
        user_data.switch_light('GREEN')
    elif car_count >= user_data.YELLOW_THRESHOLD[0] and car_count <= user_data.YELLOW_THRESHOLD[1]:
        user_data.switch_light('YELLOW')
    else:  # car_count < 5
        user_data.switch_light('RED')
        
    # Log status every frame
    user_data.log_status()

    return Gst.PadProbeReturn.OK


if __name__ == "__main__":
    """
    Main program entry point that initializes and runs the traffic light control system.
    
    The system uses Hailo AI accelerator to detect objects (cars) and controls
    traffic lights based on detection counts. Press Ctrl+C to exit gracefully.
    """
    try:
        print("Starting Traffic Light Control System")
        print("Press Ctrl+C to exit")
        
        user_data = user_app_callback_class()
        app = GStreamerDetectionApp(app_callback, user_data)
        app.run()
    except KeyboardInterrupt:
        print("Program interrupted by user.")
    finally:
        GPIO.cleanup()
        print("GPIO pins cleaned up.")
