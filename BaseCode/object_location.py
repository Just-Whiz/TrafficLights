import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp
from gpiozero import LED

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        # Configuration
        self.target_object = "person"  # Object type to detect
        
        # Target zone configuration (normalized coordinates 0-1)
        self.zone_x_min = 0.4  # Left boundary of target zone
        self.zone_x_max = 0.6  # Right boundary of target zone
        self.zone_y_min = 0.3  # Top boundary of target zone
        self.zone_y_max = 0.7  # Bottom boundary of target zone
        
        # Debouncing variables
        self.in_zone_frames = 0      # Consecutive frames with object in zone
        self.out_zone_frames = 0     # Consecutive frames without object in zone
        
        # State tracking
        self.is_it_active = False

        self.green_led = LED(18)
        self.red_led = LED(14)
        
        self.red_led.off()
        self.green_led.on()
        
def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    user_data.increment()
    
    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)
    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        frame = get_numpy_from_buffer(buffer, format, width, height)
    
    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    
    object_in_zone = False
    detection_string = ""
    
    # Parse the detections
    for detection in detections:
        label = detection.get_label()
        confidence = detection.get_confidence()
        
        if confidence > 0.4 and label == user_data.target_object:
            # Get bounding box coordinates
            bbox = detection.get_bbox()
            
            # Call the coordinate methods
            x_min = bbox.xmin()
            y_min = bbox.ymin()
            box_width = bbox.width()
            box_height = bbox.height()
            
            # Calculate max coordinates
            x_max = x_min + box_width
            y_max = y_min + box_height
            
            # Calculate center point (these are normalized 0-1)
            center_x = x_min + (box_width / 2)
            center_y = (y_min + (box_height / 2) - 0.22) * 1.83

            # Debug print for coordinates
            detection_string += (f"{label.capitalize()} detected!\n"
                               f"Position: center=({center_x:.2f}, {center_y:.2f})\n"
                               f"Bounds: xmin={x_min:.2f}, ymin={y_min:.2f}, xmax={x_max:.2f}, ymax={y_max:.2f}\n"
                               f"Confidence: {confidence:.2f}\n")
            
            # Check if object's center is in the target zone
            if (user_data.zone_x_min <= center_x <= user_data.zone_x_max and 
                (user_data.zone_y_min - 0.22) * 1.83 <= center_y <= (user_data.zone_y_max - 0.22) * 1.83):
                object_in_zone = True
                detection_string += f"Object is in target zone!\n"
    
    # Debouncing logic for zone detection
    if object_in_zone:
        user_data.in_zone_frames += 1
        user_data.out_zone_frames = 0
        
        if user_data.in_zone_frames >= 4 and not user_data.is_it_active:
            # Turn on red led, or do what ever else you want to do
            user_data.red_led.on()
            user_data.green_led.off()
            
            user_data.is_it_active = True
            print(f"{user_data.target_object.capitalize()} detected in target zone - Servo activated!")
    else:
        user_data.out_zone_frames += 1
        user_data.in_zone_frames = 0
        
        if user_data.out_zone_frames >= 5 and user_data.is_it_active:
            user_data.red_led.off()
            user_data.green_led.on()
            
            user_data.is_it_active = False
            print(f"No {user_data.target_object} in target zone - Servo deactivated!")

    # Print detections if any
    if detection_string:
        print(detection_string, end='')
    
    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()