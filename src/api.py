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
}

telemetry_history = []


def topic_login(topic):
    parts = topic.split("/")
    return parts[3] if len(parts) >= 5 else None


def update_from_payload(payload):
    device_state["timestamp"] = payload.get("timestamp", device_state["timestamp"])
    device_state["temperature"] = payload.get("temperature", device_state["temperature"])
    device_state["led_state"] = payload.get("led_state", device_state["led_state"])

    temp = payload.get("temperature")
    timestamp = payload.get("timestamp")
    if isinstance(temp, (int, float)) and isinstance(timestamp, str):
        telemetry_history.append({"timestamp": timestamp, "temperature": temp})
        if len(telemetry_history) > 2000:
            telemetry_history.pop(0)

    if "measure_period" in payload:
        device_state["measure_period"] = payload["measure_period"]
    elif "period" in payload:
        device_state["measure_period"] = payload["period"]
