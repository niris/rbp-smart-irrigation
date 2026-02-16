# Irrigo

A lightweight irrigation control system for Raspberry Pi. Manage one or more water pumps through a web dashboard — manually or on a schedule.

## Features

- **Multi-pump support** — add, remove, and name pumps mapped to GPIO pins
- **Manual mode** — select a pump and start/stop watering on demand
- **Auto mode** — schedule timed irrigations per pump (HH:MM + duration)
- **Live status** — polls pump state every 5 seconds with a water-drop animation
- **Persistent config** — mode, pumps, and schedules saved to `schedule.json`

## Requirements

- Raspberry Pi (any model with GPIO)
- Python 3
- Dependencies: `flask`, `RPi.GPIO`

## Setup

```bash
git clone <repo-url> && cd rbp-smart-irrigation
pip install -r requirements.txt
python app/api/app.py
```

The dashboard is served at `http://<pi-ip>:5000`.

## Project structure

```
app/
  api/
    app.py            # Flask backend + GPIO control + scheduler
    schedule.json     # Auto-generated config (pumps, schedules, mode)
  frontend/
    index.html        # Dashboard UI
    styles.css        # Stylesheet
    assets/images/    # SVG illustrations
```

## API

| Method | Endpoint             | Description                          |
| ------ | -------------------- | ------------------------------------ |
| GET    | `/`                  | Serve the dashboard                  |
| GET    | `/status`            | Overall + per-pump on/off status     |
| GET    | `/mode`              | Current mode, pumps, and schedules   |
| POST   | `/mode`              | Set mode (`manual` / `auto`)         |
| GET    | `/pumps`             | List all pumps                       |
| POST   | `/pumps`             | Add a pump (`name`, `pin`)           |
| DELETE | `/pumps/<id>`        | Remove a pump and its schedules      |
| POST   | `/start`             | Start a pump (`pump_id`, `duration`) |
| POST   | `/stop`              | Stop a pump (`pump_id`) or all       |
| POST   | `/schedule`          | Replace schedule list                |
| DELETE | `/schedule/<index>`  | Delete a schedule entry              |

## Default configuration

On first run, a default pump is created:

```json
{
  "id": "pump-1",
  "name": "Pump 1",
  "pin": 2
}
```

GPIO pins use BCM numbering. Pumps are active-low (LOW = on, HIGH = off).
