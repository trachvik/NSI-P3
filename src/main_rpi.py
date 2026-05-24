import network
import time
import ntptime
import json
import machine
import dht
from umqtt.robust import MQTTClient
from config import SSID, PASSWORD, MQTT_BROKER, LOGIN

toggle_counter = 0

TOPIC_PUB_TELEMETRY = f"cvut/nsi/2026/{LOGIN}/telemetry".encode('utf-8')
TOPIC_SUB_LED = f"cvut/nsi/2026/{LOGIN}/led".encode('utf-8')
# Only this device should react to period updates for this login.
TOPIC_SUB_PERIOD = f"cvut/nsi/2026/{LOGIN}/period".encode('utf-8')
TOPIC_SUB_ALL_TELEMETRY = b"cvut/nsi/2026/+/telemetry"

# Current measurement/publish period in seconds.
measure_period_s = 10


sensor = dht.DHT22(machine.Pin(20))
led = machine.Pin("LED", machine.Pin.OUT)
led.value(0)

warning_timer = machine.Timer()

publish_requested = False

def publish_isr(t):
    global publish_requested
    publish_requested = True

def warning_isr(t):
    global toggle_counter
    led.toggle()
    toggle_counter += 1
    if toggle_counter < 6:
        warning_timer.init(period=100, mode=machine.Timer.ONE_SHOT, callback=warning_isr)
    else:
        toggle_counter = 0


def connect_wifi(timeout_s=15):
    wlan.connect(SSID, PASSWORD)
    start = time.ticks_ms()
    # Wait at most timeout_s seconds.
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            return False
        time.sleep_ms(200)
    return True


def iso8601_utc_now():
    y, mo, d, h, mi, s, _, _ = time.gmtime(time.time())
    ms = time.ticks_ms() % 1000
    # Z suffix means UTC timezone (ISO 8601 TZD).
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}.{:03d}Z".format(
        y, mo, d, h, mi, s, ms
    )


def update_measure_period(new_period_s):
    global measure_period_s
    measure_period_s = new_period_s
    # Apply period update while program is running.
    publish_timer.init(period=measure_period_s * 1000, mode=machine.Timer.PERIODIC, callback=publish_isr)

def mqtt_callback(topic, msg):
    topic_str = topic.decode('utf-8')
    # Case-insensitive ON/OFF/TOGGLE commands.
    msg_str = msg.decode('utf-8').strip().upper()
    
    if topic_str == TOPIC_SUB_LED.decode('utf-8'):
        if msg_str == "ON":
            led.value(1)
            print("Incoming command: ON")
        elif msg_str == "OFF":
            led.value(0)
            print("Incoming command: OFF")
        elif msg_str == "TOGGLE":
            led.toggle()
            print("Incoming command: TOGGLE")
    elif topic_str == TOPIC_SUB_PERIOD.decode('utf-8'):
        try:
            requested_period = int(msg.decode('utf-8').strip())
            # Second validation guard directly on the device.
            if 1 <= requested_period <= 300:
                update_measure_period(requested_period)
                print("Incoming command: PERIOD={}s".format(requested_period))
            else:
                print("Invalid period: out of range 1-300 s")
        except ValueError:
            print("Invalid period: not an integer")

    elif topic_str.endswith("/telemetry"):
        # cvut/nsi/2026/<login>/telemetry => login is at index 3.
        sender_login = topic_str.split('/')[3]
        if sender_login != LOGIN:
            try:
                data = json.loads(msg.decode("utf-8"))
                temperature = data.get("temperature")
                # Ignore invalid/non-numeric temperature.
                if isinstance(temperature, (int, float)) and temperature > 30:
                    warning_timer.init(period=100, mode=machine.Timer.ONE_SHOT, callback=warning_isr)
            except ValueError:
                print("Invalid JSON")


wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.disconnect()  # Reset previous Wi-Fi state and start clean.

if not connect_wifi(timeout_s=15): # Wait up to 15 seconds for Wi-Fi connection
    raise RuntimeError("Wi-Fi connection failed")

ntptime.host = "ntp.cesnet.cz"
try:
    ntptime.settime()
except OSError:
    pass

publish_timer = machine.Timer()
publish_timer.init(period=measure_period_s * 1000, mode=machine.Timer.PERIODIC, callback=publish_isr)


client_id = f"rpi_pico_{LOGIN}_{machine.unique_id().hex()}"
client = MQTTClient(client_id=client_id, server=MQTT_BROKER)
client.set_callback(mqtt_callback)
client.connect()
client.subscribe(TOPIC_SUB_LED)
client.subscribe(TOPIC_SUB_PERIOD)
client.subscribe(TOPIC_SUB_ALL_TELEMETRY)


while True:
    # Non-blocking "asynchronous" MQTT polling.
    client.check_msg()   
    if publish_requested:
        publish_requested = False
        try:
            sensor.measure()
            payload = {
                "timestamp": iso8601_utc_now(),
                "uptime": time.ticks_ms() / 1000,
                "led_state": led.value(),
                "temperature": sensor.temperature(),
                "humidity": sensor.humidity(),
                "measure_period": measure_period_s
            }
            payload_json = json.dumps(payload)
            client.publish(TOPIC_PUB_TELEMETRY, payload_json.encode('utf-8'), qos=1)
            print(f"Published: {payload_json}")
            
        except Exception:
            pass

