import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request
from dotenv import load_dotenv

from database import (
    get_telemetry_filtered,
    get_telemetry_filtered_count,
    get_total_telemetry_count,
    is_valid_iso8601,
    create_telemetry_from_api,
    delete_device_by_id,
    delete_telemetry_by_id,
    get_device_by_id,
    get_devices,
    get_telemetry_by_id,
)


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

LOGIN = os.getenv("LOGIN")

api_bp = Blueprint("api", __name__, url_prefix="/api")


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
    # Expected format: cvut/nsi/2026/<login>/...
    parts = topic.split("/")
    return parts[3] if len(parts) >= 5 else None


def update_from_payload(payload):
    # Update "current state" shown on dashboard.
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
        # Keep short in-memory history for chart rendering.
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


def _parse_iso_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@api_bp.route("/devices", methods=["GET"])
def api_get_devices():
    # 404 when DB is empty (required by assignment).
    items = get_devices()
    if not items:
        return jsonify({"error": "No devices found"}), 404
    return jsonify(items), 200


@api_bp.route("/telemetry", methods=["GET", "POST"])
def api_telemetry_collection():
    if request.method == "POST":
        # silent=True avoids Flask exception for invalid JSON.
        payload = request.get_json(silent=True)
        result, error = create_telemetry_from_api(payload)
        if error == "Device not found":
            return jsonify({"error": error}), 404
        if error:
            return jsonify({"error": error}), 400
        return jsonify(result), 201

    device_id_raw = request.args.get("device_id")
    from_ts = request.args.get("from")
    to_ts = request.args.get("to")

    device_id = None
    if device_id_raw is not None:
        try:
            device_id = int(device_id_raw)
        except ValueError:
            return jsonify({"error": "Query parameter 'device_id' must be an integer"}), 400

    if from_ts is not None and not is_valid_iso8601(from_ts):
        return jsonify({"error": "Query parameter 'from' must be ISO 8601"}), 400

    if to_ts is not None and not is_valid_iso8601(to_ts):
        return jsonify({"error": "Query parameter 'to' must be ISO 8601"}), 400

    if from_ts is not None and to_ts is not None:
        if _parse_iso_datetime(from_ts) > _parse_iso_datetime(to_ts):
            return jsonify({"error": "Query parameter 'from' must not be greater than 'to'"}), 400

    sort_field = (request.headers.get("X-Sort-Field") or "timestamp").strip().lower()
    sort_order = (request.headers.get("X-Sort-Order") or "desc").strip().lower()

    if sort_field not in ("timestamp", "temperature"):
        return jsonify({"error": "Header 'X-Sort-Field' must be one of: timestamp, temperature"}), 400

    if sort_order not in ("asc", "desc"):
        return jsonify({"error": "Header 'X-Sort-Order' must be one of: asc, desc"}), 400

    rows = get_telemetry_filtered(
        device_id=device_id,
        from_ts=from_ts,
        to_ts=to_ts,
        sort_field=sort_field,
        sort_order=sort_order,
    )

    current_count = get_telemetry_filtered_count(device_id=device_id, from_ts=from_ts, to_ts=to_ts)
    total_count = get_total_telemetry_count()

    response = jsonify(rows)
    response.headers["X-Current-Count"] = str(current_count)
    response.headers["X-Total-Count"] = str(total_count)
    return response, 200


@api_bp.route("/devices/<int:device_id>", methods=["GET"])
def api_get_device(device_id):
    item = get_device_by_id(device_id)
    if item is None:
        return jsonify({"error": "Device not found"}), 404
    return jsonify(item), 200


@api_bp.route("/telemetry/<int:telemetry_id>", methods=["GET"])
def api_get_telemetry(telemetry_id):
    item = get_telemetry_by_id(telemetry_id)
    if item is None:
        return jsonify({"error": "Telemetry record not found"}), 404
    return jsonify(item), 200


@api_bp.route("/telemetry/<int:telemetry_id>", methods=["DELETE"])
def api_delete_telemetry(telemetry_id):
    deleted = delete_telemetry_by_id(telemetry_id)
    if not deleted:
        return jsonify({"error": "Telemetry record not found"}), 404
    return jsonify({"message": "Telemetry record deleted", "id": telemetry_id}), 200


@api_bp.route("/devices/<int:device_id>", methods=["DELETE"])
def api_delete_device(device_id):
    deleted = delete_device_by_id(device_id)
    if not deleted:
        return jsonify({"error": "Device not found"}), 404
    return jsonify({"message": "Device and related telemetry deleted", "id": device_id}), 200


