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
        self.target_object = "cup"  # Object type to detect
        
        # Debouncing variables
        self.detection_counter = 0    # Consecutive frames with exact match
        self.no_detection_counter = 0  # Consecutive frames without match
    
        # State tracking, is it active or not?
        self.is_it_active = False
        
        self.green_led = LED(18)
        self.red_led = LED(14)
        
        self.red_led.off()
        self.green_led.on()

def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    # Using the user_data to count the number of frames
    user_data.increment()
    
    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)
    # If the user_data.use_frame is set to True, we can get the video frame from the buffer
    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        frame = get_numpy_from_buffer(buffer, format, width, height)
    
    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    
    # Count objects in this frame
    object_count = 0
    detection_string = ""
    
    # Parse the detections
    for detection in detections:
        label = detection.get_label()
        confidence = detection.get_confidence()
        
        # Check for target objects with confidence threshold
        if confidence > 0.4:
            if label == user_data.target_object:
                object_count += 1
                detection_string += f"{label.capitalize()} detected! Confidence: {confidence:.2f}\n"
    
    # Debouncing logic for number of items
    if object_count >= 3:
        user_data.detection_counter += 1
        user_data.no_detection_counter = 0
        
        # Only activate after sufficient consistent frames
        if user_data.detection_counter >= 4 and not user_data.is_it_active:
            # Turn on red led, or do what ever else you want to do
            user_data.red_led.on()
            user_data.green_led.off()
            
            user_data.is_it_active = True
            print(f"NUMBER OF OBJECTS DETECTED!")
    else:
        user_data.no_detection_counter += 1
        user_data.detection_counter = 0
        
        # Only deactivate after sufficient non-matching frames
        if user_data.no_detection_counter >= 5 and user_data.is_it_active:
            # Turn on green LED or what ever else you wish to do
            user_data.red_led.off()
            user_data.green_led.on()
            
            user_data.is_it_active = False
            print(f"No longer detecting number of objects.")

    # Print detections if any
    if detection_string:
        print(f"Current {user_data.target_object} count: {object_count}")
        print(detection_string, end='')
    
    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()