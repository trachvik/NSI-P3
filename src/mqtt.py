import json
import os
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from api import LOGIN, topic_login, update_from_payload, update_status


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

MQTT_BROKER = os.getenv("MQTT_BROKER")
TOPIC_SUB_ALL_TELEMETRY = "cvut/nsi/2026/+/telemetry"
TOPIC_SUB_ALL_STATUS = "cvut/nsi/2026/+/status"
TOPIC_PUB_PERIOD = f"cvut/nsi/2026/{LOGIN}/period"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        client.subscribe(TOPIC_SUB_ALL_TELEMETRY)
        client.subscribe(TOPIC_SUB_ALL_STATUS)
        print(f"[MQTT] Connected, subscribed to {TOPIC_SUB_ALL_TELEMETRY} and {TOPIC_SUB_ALL_STATUS}")
    else:
        print(f"[MQTT] Connect failed with rc={reason_code}")


def on_message(client, userdata, msg):
    sender_login = topic_login(msg.topic)
    if (sender_login or "").strip().lower() != (LOGIN or "").strip().lower():
        return

    if msg.topic.endswith("/status"):
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

    update_from_payload(payload)


def publish_period_command(period):
    mqtt_client.publish(TOPIC_PUB_PERIOD, str(period), qos=1)
    print(f"[MQTT] Published period={period} to {TOPIC_PUB_PERIOD}")


def init_mqtt():
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
