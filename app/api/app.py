import os
import json
import uuid
import atexit
import logging
from datetime import datetime
from flask import Flask, jsonify, render_template, request
import RPi.GPIO as GPIO
import threading

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
STATIC_DIR = TEMPLATE_DIR
SCHEDULE_FILE = os.path.join(BASE_DIR, "schedule.json")

# Flask app configuration
app = Flask(
    __name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR, static_url_path=""
)

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# GPIO setup
GPIO.setmode(GPIO.BCM)

# Track pump timers keyed by pump id
pump_timers = {}
pump_lock = threading.Lock()

DEFAULT_PUMP = {"id": "pump-1", "name": "Pump 1", "pin": 2}


# --- Schedule persistence ---

def load_schedule():
    """Read schedule data from disk, returning defaults if missing."""
    try:
        with open(SCHEDULE_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("mode", "manual")
    data.setdefault("pumps", [DEFAULT_PUMP.copy()])
    data.setdefault("schedules", [])
    return data


def save_schedule(data):
    """Write schedule data to disk."""
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def setup_pump_pins(data):
    """Configure GPIO for all pumps (set as output, HIGH = off)."""
    for pump in data.get("pumps", []):
        pin = pump["pin"]
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)


# Initialize GPIO pins for existing pumps
setup_pump_pins(load_schedule())


def get_pump_by_id(data, pump_id):
    """Find a pump dict by its id, or None."""
    for pump in data.get("pumps", []):
        if pump["id"] == pump_id:
            return pump
    return None


# --- Pump helpers ---

def run_pump(pin, duration):
    """Run the pump on *pin* for *duration* seconds, then turn it off."""
    logging.info(f"Turning ON pump on pin {pin} for {duration} seconds")
    GPIO.output(pin, GPIO.LOW)  # Turn pump ON

    def _off():
        GPIO.output(pin, GPIO.HIGH)  # Turn pump OFF
        logging.info(f"Pump on pin {pin} turned OFF after {duration} seconds")

    timer = threading.Timer(duration, _off)
    timer.start()
    return timer


def stop_pump(pin=None):
    """Stop a specific pump by pin, or all pumps if pin is None."""
    with pump_lock:
        if pin is not None:
            # Stop specific pump — find its timer
            to_remove = []
            for pid, timer in pump_timers.items():
                data = load_schedule()
                pump = get_pump_by_id(data, pid)
                if pump and pump["pin"] == pin:
                    timer.cancel()
                    to_remove.append(pid)
            for pid in to_remove:
                del pump_timers[pid]
            GPIO.output(pin, GPIO.HIGH)
        else:
            # Stop all pumps
            for pid, timer in pump_timers.items():
                timer.cancel()
            pump_timers.clear()
            data = load_schedule()
            for pump in data.get("pumps", []):
                try:
                    GPIO.output(pump["pin"], GPIO.HIGH)
                except Exception:
                    pass
            logging.info("All pumps stopped")


# --- Scheduler thread ---

def scheduler_loop():
    """Background loop that triggers scheduled irrigations in auto mode."""
    last_triggered = {}
    while True:
        try:
            data = load_schedule()
            if data["mode"] == "auto":
                now = datetime.now()
                current_hhmm = now.strftime("%H:%M")
                for entry in data["schedules"]:
                    pump_id = entry.get("pump_id")
                    entry_key = entry["time"] + "|" + (pump_id or "")
                    if entry["time"] == current_hhmm and last_triggered.get(entry_key) != current_hhmm:
                        pump = get_pump_by_id(data, pump_id)
                        if pump is None:
                            continue
                        duration = entry.get("duration", 30)
                        pin = pump["pin"]
                        with pump_lock:
                            if pump_id in pump_timers:
                                pump_timers[pump_id].cancel()
                            pump_timers[pump_id] = run_pump(pin, duration)
                        last_triggered[entry_key] = current_hhmm
            else:
                last_triggered.clear()
        except Exception:
            pass
        threading.Event().wait(30)


scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()


# --- Routes ---

@app.route("/")
def home():
    return render_template("index.html")


# --- Pump CRUD ---

@app.route("/pumps", methods=["GET"])
def get_pumps():
    data = load_schedule()
    return jsonify(data.get("pumps", []))


@app.route("/pumps", methods=["POST"])
def add_pump():
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    pin = body.get("pin")
    if not name or pin is None:
        return jsonify({"error": "name and pin are required"}), 400
    try:
        pin = int(pin)
    except (ValueError, TypeError):
        return jsonify({"error": "pin must be an integer"}), 400
    data = load_schedule()
    # Prevent duplicate pins
    for p in data["pumps"]:
        if p["pin"] == pin:
            return jsonify({"error": "pin already in use"}), 400
    pump_id = "pump-" + uuid.uuid4().hex[:8]
    new_pump = {"id": pump_id, "name": name, "pin": pin}
    data["pumps"].append(new_pump)
    save_schedule(data)
    # Setup GPIO for the new pin
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)
    logging.info(f"Added pump '{name}' on pin {pin}")
    return jsonify(new_pump), 201


@app.route("/pumps/<pump_id>", methods=["DELETE"])
def delete_pump(pump_id):
    data = load_schedule()
    pump = get_pump_by_id(data, pump_id)
    if pump is None:
        return jsonify({"error": "pump not found"}), 404
    # Stop this pump if running
    with pump_lock:
        if pump_id in pump_timers:
            pump_timers[pump_id].cancel()
            del pump_timers[pump_id]
        try:
            GPIO.output(pump["pin"], GPIO.HIGH)
        except Exception:
            pass
    # Remove pump and its schedules
    data["pumps"] = [p for p in data["pumps"] if p["id"] != pump_id]
    data["schedules"] = [s for s in data["schedules"] if s.get("pump_id") != pump_id]
    save_schedule(data)
    logging.info(f"Deleted pump '{pump['name']}' (pin {pump['pin']})")
    return jsonify(data)


# --- Irrigation control ---

@app.route("/start", methods=["POST"])
def start_irrigation():
    body = request.get_json(force=True) if request.is_json else {}
    pump_id = body.get("pump_id")
    data = load_schedule()
    if not pump_id:
        # Default to first pump
        if not data["pumps"]:
            return jsonify({"error": "no pumps configured"}), 400
        pump_id = data["pumps"][0]["id"]
    pump = get_pump_by_id(data, pump_id)
    if pump is None:
        return jsonify({"error": "pump not found"}), 404
    duration = body.get("duration", 30)
    with pump_lock:
        if pump_id in pump_timers:
            pump_timers[pump_id].cancel()
        pump_timers[pump_id] = run_pump(pump["pin"], duration)
    return jsonify({"status": "on", "pump_id": pump_id, "duration": duration})


@app.route("/stop", methods=["POST"])
def stop_irrigation():
    body = request.get_json(force=True) if request.is_json else {}
    pump_id = body.get("pump_id")
    data = load_schedule()
    if pump_id:
        pump = get_pump_by_id(data, pump_id)
        if pump is None:
            return jsonify({"error": "pump not found"}), 404
        with pump_lock:
            if pump_id in pump_timers:
                pump_timers[pump_id].cancel()
                del pump_timers[pump_id]
            GPIO.output(pump["pin"], GPIO.HIGH)
        logging.info(f"Stopped pump '{pump['name']}'")
    else:
        stop_pump()
    return jsonify({"status": "off"})


@app.route("/status")
def status():
    data = load_schedule()
    pump_statuses = {}
    for pump in data.get("pumps", []):
        try:
            state = GPIO.input(pump["pin"])
            pump_statuses[pump["id"]] = "on" if state == GPIO.LOW else "off"
        except Exception:
            pump_statuses[pump["id"]] = "off"
    # Overall status: on if any pump is on
    overall = "on" if "on" in pump_statuses.values() else "off"
    return jsonify({
        "status": overall,
        "pumps": pump_statuses,
        "mode": data["mode"],
    })


@app.route("/mode", methods=["GET"])
def get_mode():
    data = load_schedule()
    return jsonify(data)


@app.route("/mode", methods=["POST"])
def set_mode():
    body = request.get_json(force=True)
    mode = body.get("mode")
    if mode not in ("manual", "auto"):
        return jsonify({"error": "mode must be 'manual' or 'auto'"}), 400
    data = load_schedule()
    data["mode"] = mode
    save_schedule(data)
    return jsonify(data)


@app.route("/schedule", methods=["POST"])
def set_schedule():
    body = request.get_json(force=True)
    schedules = body.get("schedules")
    if schedules is None:
        return jsonify({"error": "missing 'schedules'"}), 400
    data = load_schedule()
    data["schedules"] = schedules
    save_schedule(data)
    return jsonify(data)


@app.route("/schedule/<int:index>", methods=["DELETE"])
def delete_schedule(index):
    data = load_schedule()
    if index < 0 or index >= len(data["schedules"]):
        return jsonify({"error": "index out of range"}), 404
    data["schedules"].pop(index)
    save_schedule(data)
    return jsonify(data)


# Clean up GPIO on exit
def cleanup():
    stop_pump()
    GPIO.cleanup()

atexit.register(cleanup)


# --- Run Flask server ---
if __name__ == "__main__":
    try:
        logging.info("Starting Flask server on 0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000)
    finally:
        logging.info("Cleaning up GPIO pins")
        GPIO.cleanup()
