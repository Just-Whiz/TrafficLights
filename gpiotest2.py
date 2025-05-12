import RPi.GPIO as GPIO
import time

input_pins = [17, 27, 22]  # Choose your GPIO pins

GPIO.setmode(GPIO.BCM)

for pin in input_pins:
    GPIO.setup(pin, GPIO.OUT)

def set_light(index, state):
    """Sets the state of a specific light by index."""
    if 0 <= index < len(input_pins):
        GPIO.output(input_pins[index], state)
    else:
        print(f"Invalid index: {index}")

try:
    while True:
        #for i in range(len(input_pins)):
            #set_light(i, GPIO.HIGH) #turns on all lights one at a time.
            #time.sleep(0.5)
            #set_light(i, GPIO.LOW) #turns off all lights one at a time.
            #time.sleep(0.5)

        # Example of accessing and controlling individual lights:
        set_light(0, GPIO.HIGH)  # Turn on *************************************************************************light at index 0 (GPIO 17)
        time.sleep(1)
        set_light(0, GPIO.LOW)   # Turn off light at index 0
        set_light(1, GPIO.HIGH) # Turn on light at index 1 (GPIO 27)
        time.sleep(1)
        set_light(1, GPIO.LOW) # Turn off light at index 1
        set_light(2, GPIO.HIGH) # Turn on light at index 2 (GPIO 22)
        time.sleep(1)
        set_light(2, GPIO.LOW) # Turn off light at index 2
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
