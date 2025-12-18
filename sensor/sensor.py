
import math,random,asyncio,json
from multiprocessing.synchronize import Event

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

VALID_TYPES = ("temperature", "humidity", "moisture")
class Location:
    latitude,longitude=0,0
class Sensor:
    def __init__(self, sensor_id:str,sensor_type:str,enviroment_memory,location:Location|float|None=None):
        if sensor_type not in VALID_TYPES:
            raise ValueError(f"Invalid sensor_type: {sensor_type}\n Valid types: {VALID_TYPES}")
        self.sensor_id = sensor_id
        self.sensor_type= sensor_type
        self.enviroment_memory= enviroment_memory
        lat=math.degrees(math.asin(0.0))
        if isinstance(location, Location):
            lat = location.latitude
        elif isinstance(location, float):
            lat = location
        else:
            lat = 45.0
        self.latitude = lat
        self.locTempNoise = random.uniform(-1,1)
        #locational noise for each sensor
    async def getValue(self):
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "value": self.enviroment_memory[self.sensor_type],
            "time": self.enviroment_memory['time']
        }

    def __str__(self):
        return f"""Sensor - {self.sensor_id}:
        'sensor_id':'{self.sensor_id}'
        'sensor_type':'{self.sensor_type}'\n"""


def sensor_process( sensor_id, sensor_type, enviroment_memory,ready_event:Event,stop_event: Event, host="192.168.0.38", port=8883):
    sensor = Sensor(sensor_id=sensor_id, sensor_type=sensor_type, enviroment_memory=enviroment_memory)
    client = mqtt.Client(client_id=sensor_id,reconnect_on_failure=True,clean_session=False,callback_api_version=CallbackAPIVersion.VERSION1)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Sensor {sensor_id} connected to MQTT broker!")
            ready_event.set()
        else:
            print(f"Sensor {sensor_id} failed to connect, rc={rc}")
    client.on_connect = on_connect
    client.connect(host, port, 60)

    async def async_worker():
        client.loop_start()  # run MQTT network loop in background thread
        try:
            while not stop_event.is_set():
                reading = await sensor.getValue()
                topic = f"sensors/{sensor.sensor_type}/{sensor.sensor_id}"
                
                res=client.publish(topic,json.dumps(reading),qos=1)
                if res.is_published():
                    print(f"Sensor {sensor_id} published: {reading}")
                await asyncio.sleep(1)  # publish interval
        except asyncio.CancelledError:
            print(f"Sensor {sensor_id} async worker cancelled")
        finally:
            client.loop_stop()
            client.disconnect()
            print(f"Sensor {sensor_id} disconnected from MQTT broker")

    try:
        asyncio.run(async_worker())
    except KeyboardInterrupt:
        print(f"Sensor {sensor_id} process interrupted")


