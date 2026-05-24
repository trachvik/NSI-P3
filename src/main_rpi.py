import network
import time
import ntptime
import json
import machine
import dht
from umqtt.robust import MQTTClient
from secrets_local import SSID, PASSWORD, MQTT_BROKER, LOGIN

TOPIC_PUB_TELEMETRY = f"cvut/nsi/2026/{LOGIN}/telemetry".encode('utf-8')

sensor = dht.DHT22(machine.Pin(20))
led = machine.Pin("LED", machine.Pin.OUT)

publish_requested = False

def publish_isr(t):
    global publish_requested
    publish_requested = True


def connect_wifi(timeout_s=15):
    wlan.connect(SSID, PASSWORD)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            return False
        time.sleep_ms(200)
    return True


def iso8601_utc_now():
    y, mo, d, h, mi, s, _, _ = time.gmtime(time.time())
    ms = time.ticks_ms() % 1000
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}.{:03d}Z".format(
        y, mo, d, h, mi, s, ms
    )

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.disconnect()  # Disconnect from any previously connected network.

if not connect_wifi(timeout_s=15): # Wait up to 15 seconds for Wi-Fi connection
    raise RuntimeError("Wi-Fi connection failed")

ntptime.host = "ntp.cesnet.cz"
try:
    ntptime.settime()
except OSError:
    pass

publish_timer = machine.Timer()
publish_timer.init(period=10000, mode=machine.Timer.PERIODIC, callback=publish_isr)


client_id = f"rpi_pico_{LOGIN}_{machine.unique_id().hex()}"
client = MQTTClient(client_id=client_id, server=MQTT_BROKER)
#client.set_callback(mqtt_callback)
client.connect()


while True:
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
                "humidity": sensor.humidity()
            }
            payload_json = json.dumps(payload)
            client.publish(TOPIC_PUB_TELEMETRY, payload_json.encode('utf-8'), qos=1)
            print(f"Published: {payload_json}")
            
        except Exception:
            pass

