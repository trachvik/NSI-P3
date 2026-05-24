# NSI - Miniprojekt 3 (IoT + SQLite + REST API)

Tento projekt rozsiruje IoT system o:

1. ukladani telemetrie z MQTT do SQLite,
1. REST API nad ulozenymi daty,
1. pokrocile filtrovani a razeni telemetrie,
1. webovy dashboard historickych dat na /dashboard.

## Struktura projektu

- src/main_server.py - Flask aplikace (web + registrace API)
- src/mqtt.py - MQTT klient a zpracovani prichozich zprav
- src/api.py - REST API endpointy
- src/database.py - DB vrstva (validace, SQL dotazy, CRUD)
- src/matplotlib_viz.py - vykresleni grafu do PNG (base64)
- schema.sql - schema databaze (devices + measurements)
- templates/ - HTML sablony
- test_api.ps1 - rychly test pokrocileho endpointu telemetry

## Pozadavky

- Python 3.10+
- MQTT broker (vychozi broker.hivemq.com)

## Instalace

1. Vytvor virtualni prostredi a aktivuj ho.
1. Nainstaluj zavislosti:

```bash
pip install -r requirements.txt
```

1. Vytvor src/.env podle src/.env.example a dopln hodnoty.

Povinne promenne v .env:

- FLASK_SECRET_KEY
- LOGIN
- MQTT_BROKER
- DATABASE_FILE (volitelne, jinak src/telemetry.db)

## Spusteni

```bash
python src/main_server.py
```

Server standardne bezi na portu 5050.

## Databaze

Schema je ulozeno v souboru schema.sql.

Tabulky:

- devices: id, login, first_seen, last_seen, last_uptime, measure_period, message_count
- measurements: id, device_id, timestamp, temperature

Mezi measurements.device_id a devices.id je cizi klic s ON DELETE CASCADE.

Pri startu aplikace se automaticky:

1. vytvori DB soubor, pokud neexistuje,
1. aplikje schema,
1. overi sloupce tabulek,
1. pri neplatnem schematu tabulky znovu vytvori podle schema.sql.

## MQTT ingest

Odber temat:

- cvut/nsi/2026/+/telemetry
- cvut/nsi/2026/+/status

Pri prijmu telemetry:

1. zkontroluje se JSON payload,
1. z topicu se ziska login zarizeni,
1. vlozi se measurement,
1. aktualizuje/zaklada se zaznam v devices.

Nevalidni zprava aplikaci nesmi ukoncit - jen se zaloguje a ignoruje.

## REST API

Zakladni endpointy:

- GET /api/devices
- GET /api/devices/{device_id}
- GET /api/telemetry/{id}
- DELETE /api/telemetry/{id}
- DELETE /api/devices/{device_id}
- POST /api/telemetry

Pokrocile dotazovani:

- GET /api/telemetry
  - query: device_id, from, to
  - headers: X-Sort-Field (timestamp|temperature), X-Sort-Order (asc|desc)
  - response headers: X-Current-Count, X-Total-Count

## Dashboard

Historicky dashboard je dostupny na:

- /dashboard

Obsahuje:

1. vyber zarizeni,
1. absolutni okno (from, to),
1. relativni okno (velikost + jednotka second/minute/hour/day),
1. graf teploty v case.
