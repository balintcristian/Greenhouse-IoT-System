import time
import random
from datetime import datetime
import multiprocessing as mp

import numpy as np
import math
from multiprocessing import Manager
import asyncio
import paho.mqtt.client as mqtt
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from typing import List
from datetime import datetime
import argparse
from urllib.parse import quote_plus
from urllib.parse import quote_plus
import ssl

import json

class Location:
    latitude,longitude=0,0

def locTempNoise(latitude:float):
    """
    Generates a random temperature offset (noise) in Celsius for a given latitude.

    This offset simulates daily weather variation. The variation range is wider
    at mid-latitudes/poles and narrower near the equator.

    Returns:
        float: A random reading noise inside a range based on latitude
    """
    # Base variability range (e.g., 8 degrees C standard fluctuation)
    BASE_VARIABILITY = 2.0

    # Adjust variability: more stable near equator, more variable near poles
    # Scale the base variability by how far from the equator you are (0=equator, 1=pole)
    variability_scale = abs(latitude) / 90.0
    current_variability_range = BASE_VARIABILITY * (0.5 + variability_scale * 0.5)

    # Generate a random offset reading within the calculated range
    offset = random.uniform(-current_variability_range, current_variability_range)

    return round(offset, 2)
    
def logger_loop(log_queue):
    while True:
        msg = log_queue.get()
        print(msg)

class Sensor:
    VALID_TYPES = ("temperature", "humidity", "moisture")
    def __init__(self, sensor_id:str,sensor_type:str,shared_mem,location:Location|float|None=None):
        if sensor_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid sensor_type: {sensor_type}\n Valid types: {self.VALID_TYPES}")
        self.sensor_id = sensor_id
        self.sensor_type= sensor_type
        self.shared_mem= shared_mem
        lat=math.degrees(math.asin(0.0))
        if isinstance(location, Location):
            lat = location.latitude
        elif isinstance(location, float):
            lat = location
        else:
            lat = math.degrees(math.asin(0.0))
        self.latitude = lat
        self.locTempNoise = locTempNoise(lat)
        #locational noise for each sensor
    async def getValue(self):
        return {"value":round(self.shared_mem[self.sensor_type]+self.locTempNoise,2),"time":self.shared_mem['time'].isoformat()}
    
    def __str__(self):
        return f"""Sensor - {self.sensor_id}:
        'sensor_id':'{self.sensor_id}'
        'sensor_type':'{self.sensor_type}'
        'latitude':'{self.latitude}'
        'locationalNoise':'{self.locTempNoise}'\n"""

async def gateway_loop(sensors: List[Sensor], log_queue, poll_interval=0.5, mqtt_host="192.168.0.38", mqtt_port=8883):

    client = mqtt.Client(client_id="gateway-publisher", clean_session=False)
    try:
        client.connect(mqtt_host, mqtt_port)
        client.loop_start()
        log_queue.put(f"MQTT connected to {mqtt_host}:{mqtt_port}")
    except Exception as e:
        log_queue.put(f"MQTT connection failed: {e}")
        return
    
    while True:
        try:
            tasks = [sensor.getValue() for sensor in sensors]
            readings = await asyncio.gather(*tasks)
            for sensor, reading in zip(sensors, readings):
                topic = f"sensors/{sensor.sensor_type}/{sensor.sensor_id}"
                payload = json.dumps({
                    "value": reading.get("value"),
                    "time": reading.get("time")
                })
                try:
                    client.publish(topic, payload, qos=1, retain=True)
                    log_queue.put(f"Published {payload} to {topic}")
                except Exception as e:
                    log_queue.put(f"MQTT publish error for {sensor.sensor_id}: {e}")
            await asyncio.sleep(poll_interval)
        except Exception as e:
            log_queue.put(f"Gateway loop error: {e}")

class EnvironmentState:
    """Tracks environment variables and gradual control tilts"""
    def __init__(self, latitude=None):
        self.latitude = latitude if latitude is not None else math.degrees(math.asin(0.0))
        self.temperature = 15.0
        self.humidity = 70.0
        self.moisture = random.uniform(300, 600)
        self.time = datetime.now()
        self.start_time = time.time()
        
        # Gradual control tilts
        self.temp_tilt = 0.0
        self.hum_tilt = 0.0
        self.moist_tilt = 0.0


def temperature_func(t_days, env, fan=False, heater=False, alpha=0.01):
    """
    Realistic Earth-like temperature model:
    - Very small seasonal variation at equator
    - Large swing near poles
    - Daily cycle
    - Slowly growing climate noise
    - Gradual heater/fan tilt
    """

    # ===== 1. Baseline temperature by latitude =====
    # Realistic approximation:
    #   Equator ~27°C, mid-lat ~15°C, poles ~ -5°C
    lat_norm = abs(env.latitude) / 90.0
    BASE_TEMP = 27 - 22 * lat_norm     # 27→5°C

    # ===== 2. Seasonal amplitude by latitude =====
    # Equator ~1°C, mid-lat ~10°C, poles ~25°C
    A_seasonal = 1 + 24 * lat_norm

    # Peak at mid-year (day ~182)
    seasonal = A_seasonal * np.sin(2 * np.pi * (t_days / 365 - 0.25))

    # ===== 3. Daily cycle =====
    A_daily = 4 - 2 * lat_norm        # equator 4°C swing → poles 2°C
    frac = t_days % 1
    daily = A_daily * np.sin(2 * np.pi * frac - np.pi/2)

    # ===== 4. Slowly increasing noise =====
    years_passed = (time.time() - env.start_time) / (365*24*3600)
    noise_std = 0.3 + 0.02 * years_passed
    noise = np.random.normal(0, noise_std)

    # ===== 5. Combine base model =====
    temp = BASE_TEMP + seasonal + daily + noise

    # ===== 6. Gradual heater/fan tilt (your requirement) =====
    target_delta = 0
    if fan: target_delta -= 3
    if heater: target_delta += 3

    env.temp_tilt += alpha * (target_delta - env.temp_tilt)
    temp += env.temp_tilt

    return temp

def humidity_func(temp, moisture, t_days, env, humidifier=False, dehumidifier=False, alpha=0.01):
    """Humidity depends on temperature, moisture, diurnal cycle, and gradual controls"""
    base_humidity = 70.0
    hum = base_humidity - 0.5 * max(temp, 0)
    
    # Diurnal and moisture effects
    daily = 5 * np.sin(2 * np.pi * (t_days % 1))
    moisture_effect = (moisture - 500) / 200.0
    hum += daily + moisture_effect
    
    # Noise
    hum += np.random.normal(0, 3)
    
    # Gradual control tilt
    target_delta = 0.0
    if humidifier: target_delta += 10.0
    if dehumidifier: target_delta -= 10.0
    env.hum_tilt += alpha * (target_delta - env.hum_tilt)
    hum += env.hum_tilt
    
    return float(np.clip(hum, 0, 100))

def evaporation_rate(soil_moisture, temperature, humidity, t_day):
    """Dynamic evaporation rate in mm/day"""
    if soil_moisture > 700:
        base_evap = random.uniform(2, 12)
    else:
        base_evap = 0.0
    
    evap_max = 1.5
    evap = evap_max * max(temperature / 25, 0) * (1 - humidity / 100)
    
    diurnal_factor = max(0, np.sin(2 * np.pi * t_day))
    evap *= diurnal_factor
    
    return min(evap + base_evap, 12)

def moisture_func(prev_moisture, temperature, humidity, t_day, env, pump=False, alpha=0.01):
    """Update soil moisture with evaporation and gradual pump effect"""
    evap_mm_day = evaporation_rate(prev_moisture, temperature, humidity, t_day)
    evap_per_sec = evap_mm_day / (24*60*60)
    moisture = prev_moisture - evap_per_sec
    
    # Gradual pump tilt
    target_delta = 0.0
    if pump: target_delta += 50.0
    env.moist_tilt += alpha * (target_delta - env.moist_tilt)
    moisture += env.moist_tilt
    
    return float(np.clip(moisture, 0, 1000))

def environment_process(shared_mem, ready_event, time_acceleration=24):
    """
    Environment simulation loop.
    time_acceleration: number of simulated seconds per real second (24 = 1 real hour = 1 simulated day)
    """
    env = EnvironmentState()
    
    alpha = 0.01  # tilt smoothing factor
    
    while True:
        # Accelerated simulation time
        t_sim = (time.time() - env.start_time) * time_acceleration
        t_days = t_sim / (24*60*60)
        # Read controls
        fan = shared_mem.get('fan', False)
        heater = shared_mem.get('heater', False)
        pump = shared_mem.get('pump', False)
        humidifier = shared_mem.get('humidifier', False)
        dehumidifier = shared_mem.get('dehumidifier', False)

        shared_mem['temperature'] = round(temperature_func(t_days, env, fan, heater, alpha), 2)
        shared_mem['humidity'] = round(moisture_func(env.moisture, env.temperature, env.humidity, t_days, env, pump, alpha), 2)
        shared_mem['moisture'] = round(humidity_func(env.temperature, env.moisture, t_days, env, humidifier, dehumidifier, alpha), 2)
        shared_mem['time'] = datetime.now()
        ready_event.set()
        time.sleep(1)
def mqtt_to_mongodb_loop(mongo_name, mongo_pass, mongo_cluster, log_queue,
                         mqtt_host="192.168.0.38", mqtt_port=8883):
    subscribed = False  # outside on_connect

    def on_connect(client, userdata, flags, rc):
        nonlocal subscribed
        if rc == 0:
            log_queue.put("MQTT connected (rc=0).")
            if not subscribed:
                client.subscribe("sensors/#", qos=1)
                subscribed = True
        else:
            log_queue.put(f"MQTT connection error: rc={rc}")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            topic_parts = msg.topic.split('/')
            if len(topic_parts) < 3:
                log_queue.put(f"Invalid topic format: {msg.topic}")
                return
            sensor_type = topic_parts[1]
            sensor_id = topic_parts[2]
            result=db[sensor_type].insert_one({
                "sensor_id": sensor_id,
                "sensor_type": sensor_type,
                "value": float(data["value"]),
                "timestamp": data["time"]
            })
            log_queue.put(f"Inserted into MongoDB ({sensor_type}): {result}")

        except Exception as e:
            log_queue.put(f"Error processing MQTT message: {e}")

    # Create single persistent MQTT client
    try:
        username = quote_plus(mongo_name)
        password = quote_plus(mongo_pass)
        cluster = quote_plus(mongo_cluster)
        uri = f"mongodb+srv://{username}:{password}@{cluster}/?retryWrites=true&w=majority&appName=SensorSimulator"
        log_queue.put("MongoDB connected successfully.")
    except Exception as e:
        log_queue.put(f"MongoDB connection error: {e}")
        return
    mongo_client = MongoClient(uri, server_api=ServerApi("1"))
    db = mongo_client["sensor_data"]
    client = mqtt.Client(client_id="mqtt-subscriber",clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(mqtt_host, mqtt_port)
        log_queue.put("MQTT subscriber connected, entering loop_forever()")
    except Exception as e:
        log_queue.put(f"MQTT initial connection error: {e}")
        return

    client.loop_forever()

def main():
    parser = argparse.ArgumentParser(description="MQTT Sensor Simulator")
    parser.add_argument("--mongo-name", type=str, required=True, help="mongo name")
    parser.add_argument("--mongo-pass", type=str, required=True, help="mongo pass")
    parser.add_argument("--mongo-cluster", type=str, required=True, help="mongo cluster")
    parser.add_argument("--mqtt-host", type=str, default="192.168.0.38", help="MQTT host")
    parser.add_argument("--mqtt-port", type=int, default=8883, help="MQTT port")
    args = parser.parse_args()

    manager = Manager()
    shared_mem = manager.dict()
    ready_event = mp.Event()
    try:
        log_queue = mp.Queue()
        logger_proc = mp.Process(target=logger_loop, args=(log_queue,))
        logger_proc.start()


        env_proc = mp.Process(target=environment_process,args=(shared_mem, ready_event),daemon=True)
        env_proc.start()
        print("Waiting for environment initialization...")
        ready_event.wait()  # Blocks until environment sets it
        print(f"Environment initialized")

        subscriber_proc = mp.Process(target=mqtt_to_mongodb_loop,args=(args.mongo_name, args.mongo_pass, args.mongo_cluster,log_queue, args.mqtt_host, args.mqtt_port,))
        subscriber_proc.start()

        sensors:List[Sensor] = []
        # for i in range(3):
        sensors.append(Sensor(f't{1}','temperature',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        sensors.append(Sensor(f'h{1}','humidity',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        sensors.append(Sensor(f'm{1}','moisture',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        try:
            asyncio.run(gateway_loop(sensors, log_queue, mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port,poll_interval=2))
        except Exception as e:
            log_queue.put(f"Gateway loop error: {e}")
    except KeyboardInterrupt:
        env_proc.terminate()
        subscriber_proc.terminate()
        logger_proc.terminate()

        print("Exiting...")

if __name__ == "__main__":
   main()

