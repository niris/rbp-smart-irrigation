from flask import Flask, render_template, jsonify
import RPi.GPIO as GPIO
import threading
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
STATIC_DIR = TEMPLATE_DIR 

# Initialize Flask app, specify folder for HTML templates
app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
    static_url_path=""   # makes /styles.css accessible at /styles.css
)
# GPIO pin configuration
PUMP_PIN = 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(PUMP_PIN, GPIO.OUT)
GPIO.output(PUMP_PIN, GPIO.HIGH)  # HIGH = pump off

# Function to run the pump for a given duration
def run_pump(duration):
    GPIO.output(PUMP_PIN, GPIO.LOW)   # Turn pump ON
    #time.sleep(duration)               # Keep it running for 'duration' seconds
    #GPIO.output(PUMP_PIN, GPIO.HIGH)  # Turn pump OFF

# Home page route
@app.route("/")
def home():
    return render_template("index.html")

# Start irrigation route
@app.route("/start")
def start_irrigation():
    # Start a thread to run the pump without blocking the server
    threading.Thread(target=run_pump, args=(10,)).start()
    return jsonify({"status": "on", "duration": 30})

# Stop irrigation route
@app.route("/stop")
def stop_irrigation():
    GPIO.output(PUMP_PIN, GPIO.HIGH)  # Turn pump OFF
    return jsonify({"status": "off"})

# Status route
@app.route("/status")
def status():
    state = GPIO.input(PUMP_PIN)
    return jsonify({"status": "on" if state == GPIO.LOW else "off"})

# Run Flask app on all network interfaces
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)