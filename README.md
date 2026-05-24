# NSI Mini Project 2

Asynchronous distributed IoT system with Raspberry Pi Pico W (MicroPython) and Flask backend.
Communication between device and server is implemented only via MQTT.

## Project Structure

- `src/main_rpi.py` - firmware for Raspberry Pi Pico W
- `src/main_server.py` - Flask entrypoint for dashboard
- `src/mqtt.py` - MQTT client for server
- `src/api.py` - shared in-memory state
- `src/matplotlib_viz.py` - telemetry visualization helpers
- `templates/` - HTML templates
- `requirements.txt` - Python dependencies
- `.gitignore` - ignored local files

## Requirements

- Python 3.10+
- MQTT broker (default: `broker.hivemq.com`)
- Raspberry Pi Pico W with DHT22

## Setup

1. Create and activate virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Create `src/.env` from `src/.env.example` and fill values.
2. Create `src/config.py` from `src/config.example.py` and fill values.

## Run Server

```bash
python src/main_server.py
```


## Firmware Features

- Wi-Fi connection + NTP sync (`tik.cesnet.cz`)
- Periodic telemetry publish to `cvut/nsi/2026/<login>/telemetry` with QoS 1
- LED command handling (`ON/OFF/TOGGLE`, case-insensitive)
- Dynamic period update from `cvut/nsi/2026/<login>/period`
- Alert blink when foreign telemetry reports temperature > 30 C
- LWT status reporting to `cvut/nsi/2026/<login>/status`
