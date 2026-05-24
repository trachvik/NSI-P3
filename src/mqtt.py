import json
import os
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from api import LOGIN, topic_login, update_from_payload, update_status
from database import save_telemetry


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

MQTT_BROKER = os.getenv("MQTT_BROKER")
TOPIC_SUB_ALL_TELEMETRY = "cvut/nsi/2026/+/telemetry"
TOPIC_SUB_ALL_STATUS = "cvut/nsi/2026/+/status"
TOPIC_PUB_PERIOD = f"cvut/nsi/2026/{LOGIN}/period"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def _same_login(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        # One wildcard topic for telemetry from all devices.
        client.subscribe(TOPIC_SUB_ALL_TELEMETRY)
        # Optional status topic (ONLINE/OFFLINE).
        client.subscribe(TOPIC_SUB_ALL_STATUS)
        print(f"[MQTT] Connected, subscribed to {TOPIC_SUB_ALL_TELEMETRY} and {TOPIC_SUB_ALL_STATUS}")
    else:
        print(f"[MQTT] Connect failed with rc={reason_code}")


def on_message(client, userdata, msg):
    # Login is extracted from topic: cvut/nsi/2026/<login>/...
    sender_login = topic_login(msg.topic)
    if not sender_login:
        return

    if msg.topic.endswith("/status"):
        # Dashboard status is tracked only for configured local login.
        if not _same_login(sender_login, LOGIN):
            return
        try:
            status_payload = msg.payload.decode("utf-8")
        except UnicodeError:
            print("[MQTT] Invalid status payload")
            return
        update_status(status_payload)
        return

    if not msg.topic.endswith("/telemetry"):
        return

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeError):
        print("[MQTT] Invalid telemetry payload")
        return

    normalized, error = save_telemetry(sender_login, payload)
    if error:
        # Invalid payload must not crash application.
        print(f"[MQTT] Ignored message from {sender_login}: {error}")
        return

    # Keep dashboard in-memory state only for configured local login.
    if _same_login(sender_login, LOGIN):
        payload_for_state = dict(payload)
        payload_for_state.update(normalized)
        update_from_payload(payload_for_state)


def publish_period_command(period):
    mqtt_client.publish(TOPIC_PUB_PERIOD, str(period), qos=1)
    print(f"[MQTT] Published period={period} to {TOPIC_PUB_PERIOD}")


def init_mqtt():
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
