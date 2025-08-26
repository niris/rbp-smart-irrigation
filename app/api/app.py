from flask import Flask, render_template, jsonify
import RPi.GPIO as GPIO
import threading
import os
import logging
from flask import request

# ---------------------------
# Constants
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
STATIC_DIR = TEMPLATE_DIR

DEFAULT_DURATION = 10  # seconds
# Physical pins = 11, 13, 15, 16
PUMP_PINS = [17, 27]  # BCM pin numbers for pumps
# TODO: add more pumps (15=22, 16=23)

# ---------------------------
# Flask app configuration
# ---------------------------
app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
    static_url_path=""
)

# ---------------------------
# Logging setup
# ---------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ---------------------------
# GPIO setup
# ---------------------------
GPIO.setmode(GPIO.BCM)
for pin in PUMP_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)  # OFF initially

# ---------------------------
# Helper functions
# ---------------------------
def run_pump(index: int, duration: int = DEFAULT_DURATION) -> None:
    """
    Run a pump for a given duration without blocking the Flask server.
    """
    if index < 0 or index >= len(PUMP_PINS):
        logging.warning(f"Invalid pump index: {index}")
        return

    pin = PUMP_PINS[index]
    logging.info(f"Turning ON pump {index} for {duration} seconds")
    GPIO.output(pin, GPIO.LOW)  # ON

    def turn_off():
        GPIO.output(pin, GPIO.HIGH)
        logging.info(f"Pump {index} turned OFF after {duration} seconds")

    threading.Timer(duration, turn_off).start()

def stop_pump(index: int) -> None:
    """Stop a specific pump immediately."""
    if 0 <= index < len(PUMP_PINS):
        GPIO.output(PUMP_PINS[index], GPIO.HIGH)
        logging.info(f"Pump {index} stopped")
    else:
        logging.warning(f"Invalid pump index for stop: {index}")

def stop_all_pumps() -> None:
    for pin in PUMP_PINS:
        GPIO.output(pin, GPIO.HIGH)
    logging.info("All pumps stopped")

# ---------------------------
# Flask routes
# ---------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/irrigation", methods=["POST"])
def start_irrigation():
    data = request.get_json(force=True)
    pump_id = data.get("id")
    duration = data.get("duration", DEFAULT_DURATION)
    if pump_id is None:
        return jsonify({"error": "Missing pump ID"}), 400

    if pump_id == 0:  # 0 = all pumps
        for i in range(len(PUMP_PINS)):
            run_pump(i, duration)
        return jsonify({"pumps": "all", "status": "on", "duration": duration})
    elif 1 <= pump_id <= len(PUMP_PINS):
        run_pump(pump_id - 1, duration)
        return jsonify({"pump": pump_id, "status": "on", "duration": duration})
    else:
        return jsonify({"error": "Invalid pump ID"}), 400

@app.route("/irrigation/stop", methods=["POST"])
def stop_irrigation():
    data = request.get_json(force=True)
    pump_id = data.get("id", None)
    if pump_id is None or pump_id == 0:
        stop_all_pumps()
        return jsonify({"pumps": "all", "status": "off"})
    elif 1 <= pump_id <= len(PUMP_PINS):
        stop_pump(pump_id - 1)
        return jsonify({"pump": pump_id, "status": "off"})
    else:
        return jsonify({"error": "Invalid pump ID"}), 400


@app.route("/status")
def status():
    states = {
        f"pump_{i+1}": "on" if GPIO.input(pin) == GPIO.LOW else "off"
        for i, pin in enumerate(PUMP_PINS)
    }
    return jsonify(states)

# ---------------------------
# Run Flask server
# ---------------------------
if __name__ == "__main__":
    try:
        logging.info("Starting Flask server on 0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000)
    finally:
        logging.info("Cleaning up GPIO pins")
        GPIO.cleanup()
