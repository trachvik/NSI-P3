import json
import os
from pathlib import Path

from flask import Flask, render_template, request
import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# Load LOGIN and broker from src/.env.
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

LOGIN = os.getenv("LOGIN")
MQTT_BROKER = os.getenv("MQTT_BROKER")


TOPIC_SUB_ALL_TELEMETRY = "cvut/nsi/2026/+/telemetry"
TOPIC_PUB_PERIOD = f"cvut/nsi/2026/{LOGIN}/period"


# Latest telemetry shown on the dashboard.
device_state = {
	"login": LOGIN,
	"timestamp": "-",
	"temperature": None,
	"humidity": None,
	"led_state": None,
	"measure_period": None,
}


def _topic_login(topic):
	# Topic format: cvut/nsi/2026/<login>/telemetry
	parts = topic.split("/")
	return parts[3] if len(parts) >= 5 else None


mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def on_connect(client, userdata, flags, reason_code, properties):
	if not reason_code.is_failure:
		# Subscribe once connected; updates are handled in on_message.
		client.subscribe(TOPIC_SUB_ALL_TELEMETRY)
		print(f"[MQTT] Connected, subscribed to {TOPIC_SUB_ALL_TELEMETRY}")
	else:
		print(f"[MQTT] Connect failed with rc={reason_code}")


def on_message(client, userdata, msg):
	sender_login = _topic_login(msg.topic)
	# Keep only this student's device data in dashboard state.
	if sender_login != LOGIN:
		return

	try:
		payload = json.loads(msg.payload.decode("utf-8"))
	except (ValueError, UnicodeError):
		print("[MQTT] Invalid telemetry payload")
		return

	device_state["timestamp"] = payload.get("timestamp", device_state["timestamp"])
	device_state["temperature"] = payload.get("temperature", device_state["temperature"])
	device_state["humidity"] = payload.get("humidity", device_state["humidity"])
	device_state["led_state"] = payload.get("led_state", device_state["led_state"])
	# Support both key names from different firmware variants.
	if "measure_period" in payload:
		device_state["measure_period"] = payload["measure_period"]
	elif "period" in payload:
		device_state["measure_period"] = payload["period"]


def init_mqtt():
	mqtt_client.on_connect = on_connect
	mqtt_client.on_message = on_message
	mqtt_client.connect(MQTT_BROKER, 1883, 60)
	mqtt_client.loop_start()


app = Flask(__name__, template_folder="../templates")


@app.route("/")
def index():
	return render_template("index.html", state=device_state)


@app.route("/update_telemetry_period")
def update_telemetry_period():
	# Expected URL: /update_telemetry_period?period=X
	period_raw = request.args.get("period")
	state = device_state

	if period_raw is None:
		return render_template(
			"index.html",
			state=state,
			error="Missing URL parameter 'period'.",
		), 400

	try:
		period = int(period_raw)
	except ValueError:
		return render_template(
			"index.html",
			state=state,
			error="Parameter 'period' must be an integer (seconds).",
		), 400

	if not 1 <= period <= 300:
		return render_template(
			"index.html",
			state=state,
			error="Period must be in range of 1 s to 5 min.",
		), 400

	# Valid period -> send command to device-specific MQTT topic.
	mqtt_client.publish(TOPIC_PUB_PERIOD, str(period), qos=1)
	print(f"[MQTT] Published period={period} to {TOPIC_PUB_PERIOD}")
	return render_template(
		"index.html",
		state=state,
		success=f"Period update command sent: {period} s",
	)


if __name__ == "__main__":
	init_mqtt()
	app.run(host="0.0.0.0", port=5050, debug=True)
