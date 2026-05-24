import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv

from api import api_bp, device_state, telemetry_history
from database import init_db, get_devices, get_telemetry_filtered, is_valid_iso8601
from mqtt import init_mqtt, publish_period_command
from matplotlib_viz import get_filtered_data, build_plot_url, build_history_plot_url


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
# Fail-fast: secret key is required for secure session cookies.
if not FLASK_SECRET_KEY:
    raise RuntimeError("Missing FLASK_SECRET_KEY in src/.env")


app = Flask(__name__, template_folder="../templates")
app.secret_key = FLASK_SECRET_KEY
app.register_blueprint(api_bp)

# Create/verify DB schema on server startup.
init_db()


def _convert_temp(temp_c, unit):
    # Internal storage is Celsius; convert only for UI rendering.
    if temp_c is None:
        return None
    if unit == "F":
        return (temp_c * 9.0 / 5.0) + 32.0
    return temp_c


def _get_temp_unit():
    # Temperature unit is stored in user session.
    unit = (session.get("temp_unit") or "C").upper()
    if unit not in ("C", "F"):
        unit = "C"
        session["temp_unit"] = "C"
    return unit


def _render_dashboard(error=None, success=None, args=None):
    # Shared render helper so all responses keep same page context.
    args = args or {}
    temp_unit = _get_temp_unit()

    data = get_filtered_data(telemetry_history, args)
    telemetry = data[-1] if data else None
    plot_url = build_plot_url(data, temp_unit)

    display_temperature = None
    if telemetry:
        display_temperature = _convert_temp(telemetry["temperature"], temp_unit)

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


def _dashboard_time_window(args):
    mode = (args.get("mode") or "relative").lower()
    if mode not in ("absolute", "relative"):
        mode = "relative"

    now_utc = datetime.now(timezone.utc)
    form_values = {
        "mode": mode,
        "device_id": args.get("device_id") or "",
        "from": args.get("from") or "",
        "to": args.get("to") or "",
        "window_size": args.get("window_size") or "30",
        "window_unit": (args.get("window_unit") or "minute").lower(),
    }

    if mode == "absolute":
        from_raw = (args.get("from") or "").strip()
        to_raw = (args.get("to") or "").strip()

        if not from_raw or not to_raw:
            return None, None, form_values, "For absolute mode, both 'from' and 'to' are required."
        if not is_valid_iso8601(from_raw) or not is_valid_iso8601(to_raw):
            return None, None, form_values, "Absolute mode requires ISO 8601 timestamps."

        from_dt = datetime.fromisoformat(from_raw.replace("Z", "+00:00"))
        to_dt = datetime.fromisoformat(to_raw.replace("Z", "+00:00"))
        if from_dt > to_dt:
            return None, None, form_values, "In absolute mode, 'from' must not be later than 'to'."
        return from_raw, to_raw, form_values, None

    size_raw = args.get("window_size", "30")
    unit = (args.get("window_unit") or "minute").lower()
    if unit not in ("second", "minute", "hour", "day"):
        return None, None, form_values, "Relative mode unit must be second/minute/hour/day."

    try:
        size = int(size_raw)
    except ValueError:
        return None, None, form_values, "Relative mode window size must be an integer."

    if size < 1:
        return None, None, form_values, "Relative mode window size must be at least 1."

    seconds_per_unit = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }
    window_seconds = size * seconds_per_unit[unit]

    to_dt = now_utc
    from_dt = now_utc - timedelta(seconds=window_seconds)
    from_iso = from_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    to_iso = to_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    form_values["from"] = from_iso
    form_values["to"] = to_iso
    return from_iso, to_iso, form_values, None


@app.route("/dashboard")
def dashboard_history():
    devices = get_devices()
    selected_device_raw = request.args.get("device_id")

    if not devices:
        return render_template(
            "dashboard.html",
            devices=[],
            form_values={
                "mode": "relative",
                "device_id": "",
                "from": "",
                "to": "",
                "window_size": "30",
                "window_unit": "minute",
            },
            error="No registered devices found.",
            plot_url=None,
            points_count=0,
            selected_login=None,
        )

    selected_device_id = devices[0]["id"]
    if selected_device_raw:
        try:
            selected_device_id = int(selected_device_raw)
        except ValueError:
            pass

    from_ts, to_ts, form_values, error = _dashboard_time_window(request.args)
    form_values["device_id"] = str(selected_device_id)

    selected_login = next((d["login"] for d in devices if d["id"] == selected_device_id), "-")

    rows = []
    if error is None:
        rows = get_telemetry_filtered(
            device_id=selected_device_id,
            from_ts=from_ts,
            to_ts=to_ts,
            sort_field="timestamp",
            sort_order="asc",
        )

    temp_unit = _get_temp_unit()
    plot_url = build_history_plot_url(rows, temp_unit=temp_unit)

    return render_template(
        "dashboard.html",
        devices=devices,
        form_values=form_values,
        error=error,
        plot_url=plot_url,
        points_count=len(rows),
        selected_login=selected_login,
        temp_unit=temp_unit,
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
    # Expected format: /update_telemetry_period?period=X
    period_raw = request.args.get("period")
    if period_raw is None:
        return _render_dashboard(error="Missing URL parameter 'period'.", args=request.args), 400

    try:
        period = int(period_raw)
    except ValueError:
        return _render_dashboard(error="Parameter 'period' must be an integer (seconds).", args=request.args), 400

    if not 1 <= period <= 300:
        return _render_dashboard(error="Period must be in range of 1 s to 5 min.", args=request.args), 400

    # Valid input -> publish command via MQTT.
    publish_period_command(period)
    return _render_dashboard(success=f"Period update command sent: {period} s", args=request.args)


if __name__ == "__main__":
    # MQTT listener runs in background thread.
    init_mqtt()
    app.run(host="0.0.0.0", port=5050, debug=True, use_reloader=False)
