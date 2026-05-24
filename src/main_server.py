import os
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv

from api import device_state, telemetry_history
from mqtt import init_mqtt, publish_period_command
from matplotlib_viz import get_filtered_data, build_plot_url


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
	raise RuntimeError("Missing FLASK_SECRET_KEY in src/.env")


app = Flask(__name__, template_folder="../templates")
app.secret_key = FLASK_SECRET_KEY


def _convert_temp(temp_c, unit):
	if temp_c is None:
		return None
	return temp_c if unit == "C" else (temp_c * 9.0 / 5.0) + 32.0


def _render_dashboard(error=None, success=None, args=None):
	args = args or {}
	temp_unit = (session.get("temp_unit") or "C").upper()
	if temp_unit not in ("C", "F"):
		temp_unit = "C"
		session["temp_unit"] = "C"

	data = get_filtered_data(telemetry_history, args)
	plot_url = build_plot_url(data, temp_unit)
	telemetry = data[-1] if data else None
	display_temperature = _convert_temp(telemetry["temperature"], temp_unit) if telemetry else None
	return render_template(
		"index.html",
		state=device_state,
		telemetry=telemetry,
		display_temperature=display_temperature,
		temp_unit=temp_unit,
		plot_url=plot_url,
		limit_n=args.get("limit_n", 30),
		error=error,
		success=success,
	)


@app.route("/")
def index():
	return _render_dashboard(args=request.args)


@app.route("/set_temperature_unit", methods=["POST"])
def set_temperature_unit():
	unit = (request.form.get("temp_unit") or "C").upper()
	if unit not in ("C", "F"):
		unit = "C"
	session["temp_unit"] = unit
	limit_n = request.form.get("limit_n", 30)
	return redirect(url_for("index", limit_n=limit_n))


@app.route("/update_telemetry_period")
def update_telemetry_period():
	# Expected URL: /update_telemetry_period?period=X
	period_raw = request.args.get("period")

	if period_raw is None:
		return _render_dashboard(error="Missing URL parameter 'period'.", args=request.args), 400

	try:
		period = int(period_raw)
	except ValueError:
		return _render_dashboard(error="Parameter 'period' must be an integer (seconds).", args=request.args), 400

	if not 1 <= period <= 300:
		return _render_dashboard(error="Period must be in range of 1 s to 5 min.", args=request.args), 400

	# Valid period -> send command to device-specific MQTT topic.
	publish_period_command(period)
	return _render_dashboard(success=f"Period update command sent: {period} s", args=request.args)


if __name__ == "__main__":
	init_mqtt()
	# Same as L09 approach: keep one process so in-memory telemetry is consistent.
	app.run(host="0.0.0.0", port=5050, debug=True, use_reloader=False)
