import paho.mqtt.client as mqtt
import json
import random
import time


MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_SENSORS = "sensors/data"
MQTT_TOPIC_ACTUATOR = "actuator/control"


def simulate_sensors():
    return {
        "temperature": random.uniform(20, 40),
        "vibration": random.uniform(0, 10),
        "presence": random.choice([0, 1])
    }

def on_publish(client, userdata, mid):
    print("Dados publicados no MQTT")

client = mqtt.Client()
client.on_publish = on_publish
client.connect(MQTT_BROKER, MQTT_PORT)

while True:
    data = simulate_sensors()
    if data["temperature"] > 35:
        client.publish(MQTT_TOPIC_ACTUATOR, json.dumps({"cooler": 1}))
    else:
        client.publish(MQTT_TOPIC_ACTUATOR, json.dumps({"cooler": 0}))
    print(f"Publicando dados: ", {json.dumps(data)})
    client.publish(MQTT_TOPIC_SENSORS, json.dumps(data))
    
    time.sleep(5)