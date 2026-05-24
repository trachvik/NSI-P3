import os
from pathlib import Path

from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

LOGIN = os.getenv("LOGIN")


device_state = {
    "login": LOGIN,
    "timestamp": "-",
    "temperature": None,
    "led_state": None,
    "measure_period": None,
    "status": "UNKNOWN",
}

telemetry_history = []


def topic_login(topic):
    parts = topic.split("/")
    return parts[3] if len(parts) >= 5 else None


def update_from_payload(payload):
    if "timestamp" in payload:
        device_state["timestamp"] = payload["timestamp"]
    if "temperature" in payload:
        device_state["temperature"] = payload["temperature"]
    if "led_state" in payload:
        device_state["led_state"] = payload["led_state"]

    temp = payload.get("temperature")
    try:
        temp_value = float(temp)
    except (TypeError, ValueError):
        temp_value = None
    timestamp = payload.get("timestamp")
    if temp_value is not None and isinstance(timestamp, str):
        telemetry_history.append({"timestamp": timestamp, "temperature": temp_value})
        if len(telemetry_history) > 2000:
            telemetry_history.pop(0)

    if "measure_period" in payload:
        device_state["measure_period"] = payload["measure_period"]
    elif "period" in payload:
        device_state["measure_period"] = payload["period"]


def update_status(status_payload):
    status = (status_payload or "").strip().upper()
    if status in ("ONLINE", "OFFLINE"):
        device_state["status"] = status
