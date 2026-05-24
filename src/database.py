import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

DB_FILE = os.getenv("DATABASE_FILE", str(Path(__file__).with_name("telemetry.db")))
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"

EXPECTED_COLUMNS = {
    "devices": {
        "id",
        "login",
        "first_seen",
        "last_seen",
        "last_uptime",
        "measure_period",
        "message_count",
    },
    "measurements": {
        "id",
        "device_id",
        "timestamp",
        "temperature",
    },
}


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _has_valid_schema(conn):
    for table_name, required in EXPECTED_COLUMNS.items():
        columns = _get_table_columns(conn, table_name)
        if not required.issubset(columns):
            return False
    return True


def init_db():
    conn = get_db_connection()
    try:
        if not SCHEMA_FILE.exists():
            raise RuntimeError(f"Missing schema file: {SCHEMA_FILE}")

        # Create tables if they do not exist.
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

        # If schema is wrong, recreate tables from schema.sql.
        if not _has_valid_schema(conn):
            conn.execute("DROP TABLE IF EXISTS measurements")
            conn.execute("DROP TABLE IF EXISTS devices")
            conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
            if not _has_valid_schema(conn):
                raise RuntimeError("Database schema is not valid")

        conn.commit()
    finally:
        conn.close()


def _is_valid_iso8601(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_telemetry_payload(payload):
    if not isinstance(payload, dict):
        return None, "Payload is not a JSON object"

    # Required by assignment.
    required_fields = ["temperature", "timestamp", "measure_period", "uptime"]
    missing = [field for field in required_fields if field not in payload]
    if missing:
        return None, f"Missing fields: {', '.join(missing)}"

    if not _is_valid_iso8601(payload.get("timestamp")):
        return None, "Invalid timestamp format"

    try:
        temperature = float(payload.get("temperature"))
    except (TypeError, ValueError):
        return None, "Invalid temperature"

    try:
        measure_period = int(payload.get("measure_period"))
    except (TypeError, ValueError):
        return None, "Invalid measure_period"

    try:
        uptime = float(payload.get("uptime"))
    except (TypeError, ValueError):
        return None, "Invalid uptime"

    normalized = {
        "temperature": temperature,
        "timestamp": payload.get("timestamp"),
        "measure_period": measure_period,
        "uptime": uptime,
    }
    return normalized, None


def save_telemetry(login, payload):
    normalized, error = validate_telemetry_payload(payload)
    if error:
        return None, error

    conn = get_db_connection()
    try:
        device = conn.execute(
            "SELECT id, message_count FROM devices WHERE login = ?",
            (login,),
        ).fetchone()

        if device is None:
            # First message from this login => create device row.
            conn.execute(
                """
                INSERT INTO devices (login, first_seen, last_seen, last_uptime, measure_period, message_count)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    login,
                    normalized["timestamp"],
                    normalized["timestamp"],
                    normalized["uptime"],
                    normalized["measure_period"],
                ),
            )
            device = conn.execute(
                "SELECT id, message_count FROM devices WHERE login = ?",
                (login,),
            ).fetchone()
        else:
            # Existing device => update last stats and increment count.
            conn.execute(
                """
                UPDATE devices
                SET last_seen = ?,
                    last_uptime = ?,
                    measure_period = ?,
                    message_count = ?
                WHERE id = ?
                """,
                (
                    normalized["timestamp"],
                    normalized["uptime"],
                    normalized["measure_period"],
                    device["message_count"] + 1,
                    device["id"],
                ),
            )

        # Insert one measurement row for each valid message.
        conn.execute(
            "INSERT INTO measurements (device_id, timestamp, temperature) VALUES (?, ?, ?)",
            (device["id"], normalized["timestamp"], normalized["temperature"]),
        )

        conn.commit()
        return normalized, None
    finally:
        conn.close()


def get_devices():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT login, first_seen, last_seen, last_uptime, measure_period, message_count
            FROM devices
            ORDER BY login ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_device(login):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT login, first_seen, last_seen, last_uptime, measure_period, message_count
            FROM devices
            WHERE login = ?
            """,
            (login,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_measurements(login=None, limit=100):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100

    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000

    conn = get_db_connection()
    try:
        if login:
            rows = conn.execute(
                """
                SELECT d.login, m.timestamp, m.temperature
                FROM measurements m
                JOIN devices d ON d.id = m.device_id
                WHERE d.login = ?
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (login, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.login, m.timestamp, m.temperature
                FROM measurements m
                JOIN devices d ON d.id = m.device_id
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        data = [dict(row) for row in rows]
        data.reverse()
        return data
    finally:
        conn.close()
