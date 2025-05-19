import gi
import threading
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from gi.repository import Gst
import os
import numpy as np
import cv2
import hailo
import time
import signal
import sys
import RPi.GPIO as GPIO
from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

Gst.init(None)

# Logging
ENABLE_DEBUG_LOGS = True

log_file_path = "/tmp/person_detection_log.txt"
log_formatter = logging.Formatter(f'%(asctime)s - Frame: %(frame)d - LED: %(led)s - Objects: %(objects)s - People count: %(message)s')
log_handler = RotatingFileHandler(log_file_path, maxBytes=1024 * 1024, backupCount=3)
log_handler.setFormatter(log_formatter)
logging.getLogger().handlers = []
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

# GPIO pin control
LIGHT1_PINS = [17, 27, 22]
LIGHT2_PINS = [23, 24, 25]
LIGHT3_PINS = [5, 6, 13]

GPIO.setmode(GPIO.BCM)

class GPIORelayController:
    def __init__(self, pin_map):
        self.pin_map = pin_map
        for pin in self.pin_map:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)  # Start with all lights turned off

    def set_light(self, index, state):
        """Turns on the specific color light."""
        if 0 <= index < len(self.pin_map):
            GPIO.output(self.pin_map[index], state)
        else:
            print(f"Invalid index {index}")

    def light_off(self, index, state):
        """Turns off the specific color light."""
        if 0 <= index < len(self.pin_map):
            GPIO.output(self.pin_map[index], state)
        else:
            print(f"Invalid index: {index}")
    
    def all_off(self):
        """Turns all lights in a traffic module off"""
        for light in len(self.pin_map):
            GPIO.output(self.pint_map[light], GPIO.HIGH)


class HailoDetectionApp(app_callback_class):
    def __init__(self):
        super().__init__()

        self.light1 = GPIORelayController(LIGHT1_PINS)
        self.light2 = GPIORelayController(LIGHT2_PINS)
        self.light3 = GPIORelayController(LIGHT3_PINS)

        self.target_object = "person"
        self.confidence_threshold = 0.4
        self.detection_threshold = 4
        self.no_detection_threshold = 5

        self.detection_counter = 0
        self.no_detection_counter = 0
        self.current_person_count = 0

        self.relay_lock = threading.Lock()
        self.relay_thread = threading.Thread(target=self.relay_loop, daemon=True)
        self.relay_commands = []
        self.relay_thread.start()

    def enqueue_command(self, command):
        with self.relay_lock:
            self.relay_commands.append(command)

    def relay_loop(self):
        while True:
            with self.relay_lock:
                commands = self.relay_commands[:]
                self.relay_commands.clear()
            for command in commands:
                try:
                    command()
                except Exception as e:
                    logging.error(f"Relay command failed: {e}")
            time.sleep(0.001)

    def turn_on_light1(self):
        self.light1.set_light(0, GPIO.LOW)
        self.light1.set_light(1, GPIO.LOW)
        self.light1.set_light(2, GPIO.LOW)
        self.light2.all_off()
        self.light3.all_off()

    def turn_on_light2(self):
        self.light2.set_light(0, GPIO.LOW)
        self.light2.set_light(1, GPIO.LOW)
        self.light2.set_light(2, GPIO.LOW)
        self.light1.all_off()
        self.light3.all_off()

    def turn_on_light3(self):
        self.light3.set_light(0, GPIO.LOW)
        self.light3.set_light(1, GPIO.LOW)
        self.light1.set_light(2, GPIO.LOW)
        self.light1.all_off()
        self.light2.all_off()

    def update_led_based_on_count(self, count):
        if count == 0:
            self.turn_off_all_lights()
        elif count == 1:
            self.turn_on_light1()
        elif count == 2:
            self.turn_on_light2()
        elif count >= 3:
            self.turn_on_light3()
        else:
            self.turn_off_all_lights()

    def shutdown_controllers(self):
        self.turn_off_all_lights()
        time.sleep(0.1)
        GPIO.cleanup()

def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()

    format, width, height = get_caps_from_pad(pad)
    if not format or not width or not height:
        return Gst.PadProbeReturn.OK

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    object_count = 0
    detection_details = []

    for detection in detections:
        label = detection.get_label()
        confidence = detection.get_confidence()
        if confidence > user_data.confidence_threshold and label == user_data.target_object:
            object_count += 1
        detection_details.append(f"{label} ({confidence:.2f})")
        logging.info(
            str(object_count), 
            extra={
                'frame': user_data.frame_count,
                'led': f"Light1, Light2, Light3",
                'objects': ', '.join(detection_details)
                }
                )

    user_data.current_person_count = object_count

    if object_count >= 1:
        user_data.detection_counter += 1
        user_data.no_detection_counter = 0
        if user_data.detection_counter >= user_data.detection_threshold:
            user_data.is_active = True
            user_data.update_led_based_on_count(object_count)
    else:
        user_data.no_detection_counter += 1
        user_data.detection_counter = 0
        if user_data.no_detection_counter >= user_data.no_detection_threshold:
            user_data.is_active = False
            user_data.update_led_based_on_count(0)

    return Gst.PadProbeReturn.OK

def main():
    user_data = HailoDetectionApp()

    try:
        app = GStreamerDetectionApp(app_callback, user_data)
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in main application: {e}")
    finally:
        user_data.shutdown_controllers()
        GPIO.cleanup()

if __name__ == "__main__":
    main()

