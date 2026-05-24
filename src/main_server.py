from flask import Flask, render_template, request

from api import device_state, telemetry_history
from mqtt import init_mqtt, publish_period_command
from matplotlib_viz import get_filtered_data, build_plot_url


app = Flask(__name__, template_folder="../templates")


def _render_dashboard(error=None, success=None, args=None):
	args = args or {}
	data = get_filtered_data(telemetry_history, args)
	plot_url = build_plot_url(data)
	return render_template(
		"index.html",
		state=device_state,
		telemetry=data[-1] if data else None,
		plot_url=plot_url,
		limit_n=args.get("limit_n", 30),
		error=error,
		success=success,
	)


@app.route("/")
def index():
	return _render_dashboard(args=request.args)


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
