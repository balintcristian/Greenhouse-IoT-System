import numpy as np
import math
import random
import time
from datetime import datetime
import multiprocessing as mp
import queue  # for Empty exception
from multiprocessing import Manager,queues
from typing import List
import asyncio
import paho.mqtt.client as mqtt
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

import argparse
from urllib.parse import quote_plus
from urllib.parse import quote_plus
import json

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import threading


class Location:
    latitude,longitude=0,0



def logger_loop(log_queue, stop_event):
    while not stop_event.is_set():
        try:
            msg = log_queue.get(timeout=0.5)
            if msg is None:
                continue
            print(msg)
        except queue.Empty:
            continue
        except OSError:
            break

VALID_TYPES = ("temperature", "humidity", "moisture")
class Sensor:
    def __init__(self, sensor_id:str,sensor_type:str,shared_mem,location:Location|float|None=None):
        if sensor_type not in VALID_TYPES:
            raise ValueError(f"Invalid sensor_type: {sensor_type}\n Valid types: {VALID_TYPES}")
        self.sensor_id = sensor_id
        self.sensor_type= sensor_type
        self.shared_mem= shared_mem
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
        return {"value":round(self.shared_mem[self.sensor_type]+self.locTempNoise,2),"time":self.shared_mem['time'].isoformat()}
    
    def __str__(self):
        return f"""Sensor - {self.sensor_id}:
        'sensor_id':'{self.sensor_id}'
        'sensor_type':'{self.sensor_type}'
        'latitude':'{self.latitude}'
        'locationalNoise':'{self.locTempNoise}'\n"""

class Actuator:
    def __init__(self,id:str,type:str,shared_mem,log_queue,is_on=False,mode:str|None=None):
        if type not in VALID_TYPES:
            raise ValueError(f"Invalid actuator type: {type}\n Valid types: {VALID_TYPES}")
        self.id=id
        self.type=type
        self.shared_mem=shared_mem
        self.log_queue=log_queue
        self.is_on=is_on
        self.device = self._assign_device(mode)
        if self.device not in shared_mem:
            shared_mem[self.device] = False
    def _assign_device(self, mode):
        """Assign correct device based on actuator type and mode."""

        device_map = {
            "temperature": ["heater", "fan"],
            "moisture": ["pump"],
            "humidity": ["humidifier", "dehumidifier"]
        }

        valid_devices = device_map[self.type]

        # If only one device exists, return it
        if len(valid_devices) == 1:
            return valid_devices[0]

        # If multiple devices exist (temperature or humidity):
        if mode is None:
            raise ValueError(
                f"Actuator type '{self.type}' requires a mode: {valid_devices}"
            )

        if mode not in valid_devices:
            raise ValueError(
                f"Invalid mode '{mode}' for type '{self.type}'. "
                f"Choose one of: {valid_devices}"
            )

        return mode
    
    def toggleActuator(self):
        new_state = not self.is_on
        try:
            self.log_queue.put_nowait(
                f"{self.id} ({self.type}:{self.device}) toggled {'ON' if new_state else 'OFF'}"
            )
            self.log_queue.put_nowait(
                f"Device '{self.device}' is now {'running' if new_state else 'stopped'}"
            )
        except Exception:
            print(f"[LOG-FAIL] {self.id} toggled {'ON' if new_state else 'OFF'}")
        self.is_on = new_state
        self.shared_mem[self.device] = new_state



async def gateway_loop(sensors: List[Sensor],actuators:List[Actuator], log_queue:mp.Queue, poll_interval=2, mqtt_host="192.168.0.38", mqtt_port=8883):
    client = mqtt.Client(client_id="gateway-publisher", clean_session=False)
    try:
        client.connect(mqtt_host, mqtt_port)
        client.loop_start()
        log_queue.put_nowait(f"MQTT connected to {mqtt_host}:{mqtt_port}")
    except Exception as e:
        log_queue.put_nowait(f"MQTT connection failed: {e}")
        return
    while True:
        count=0
        for sensor in sensors:
            count +=1
        if count<1:
            raise Exception("No sensors present")
        try:
            tasks = [sensor.getValue() for sensor in sensors]
            readings = await asyncio.gather(*tasks)
            for sensor, reading in zip(sensors, readings):
                topic = f"sensors/{sensor.sensor_type}/{sensor.sensor_id}"
                temp_val=reading.get('value')
                payload = json.dumps({
                    "value": reading.get("value"),
                    "time": reading.get("time")
                })
                try:
                    specificActuator:Actuator=next(a for a in actuators if a.device=="heater")
                    if temp_val:
                        if specificActuator.is_on==False and temp_val<15:
                            specificActuator.toggleActuator()
                        elif specificActuator.is_on==True and temp_val>20:
                            specificActuator.toggleActuator()
                        else:
                            pass
                    client.publish(topic, payload, qos=1, retain=True)
                    log_queue.put_nowait(f"Published {payload} to {topic}")
                except Exception as e:
                    log_queue.put_nowait(f"MQTT publish error for {sensor.sensor_id}: {e}")
            await asyncio.sleep(poll_interval)
        except Exception as e:
            log_queue.put_nowait(f"Gateway loop error: {e}")

class EnvironmentState:
    """Tracks environment variables and gradual control tilts"""
    def __init__(self, latitude=None):
        self.latitude = latitude if latitude is not None else math.degrees(math.asin(0.0))
        self.temperature = random.uniform(15, 20)
        self.humidity = 70.0
        self.moisture = random.uniform(300, 600)
        self.time = datetime.now()
        self.start_time = time.time()
        self.start_day=90
        # Gradual control tilts
        self.temp_tilt = 0.0
        self.hum_tilt = 0.0
        self.moist_tilt = 0.0

    def temperature_func(self, t_days, fan=False, heater=False, alpha=0.05):
        """
        Realistic Earth-like temperature function with wide but realistic variations.
        """

        # Normalize latitude
        lat_norm = abs(self.latitude) / 90.0  # 0=equator, 1=pole

        # BASE temperature: equator 27°C, mid-lat 15°C, poles -5°C
        BASE_TEMP = 27 - 32 * lat_norm  # 27→-5°C

        # Seasonal amplitude: small at equator, bigger at poles
        A_seasonal = 3 + 20 * lat_norm  # equator 3°C, poles 23°C
        seasonal = A_seasonal * np.sin(2 * np.pi * (t_days / 365 - 0.25))

        # Daily amplitude: larger at equator, smaller at poles
        A_daily = 8 - 6 * lat_norm  # equator 8°C, poles 2°C
        frac = t_days % 1
        daily = A_daily * np.sin(2 * np.pi * frac - np.pi/2)

        # Noise
        years_passed = (time.time() - self.start_time) / (365*24*3600)
        noise_std = 0.3 + 0.02 * years_passed
        noise = np.random.normal(0, noise_std)

        # Combine
        temp = BASE_TEMP + seasonal + daily + noise

        # Gradual fan/heater tilt
        target_delta = 0
        if fan: target_delta -= 3
        if heater: target_delta += 3
        self.temp_tilt += alpha * (target_delta - self.temp_tilt)
        temp += self.temp_tilt

        # Clamp to realistic Earth-like limits
        temp = max(min(temp, 50), -20)

        self.temperature = temp
        return temp

    def humidity_func(self, t_days, humidifier=False, dehumidifier=False, alpha=0.01):
        """Humidity depends on temperature, moisture, diurnal cycle, and gradual controls"""
        base_humidity = 70.0
        hum = base_humidity - 0.5 * max(self.temperature, 0)
        
        # Diurnal and moisture effects
        daily = 5 * np.sin(2 * np.pi * (t_days % 1))
        moisture_effect = (self.moisture - 500) / 200.0
        hum += daily + moisture_effect
        
        # Noise
        hum += np.random.normal(0, 3)
        
        # Gradual control tilt
        target_delta = 0.0
        if humidifier: target_delta += 10.0
        if dehumidifier: target_delta -= 10.0
        self.hum_tilt += alpha * (target_delta - self.hum_tilt)
        hum += self.hum_tilt
        self.humidity=float(np.clip(hum, 0, 100))
        return float(np.clip(hum, 0, 100))

    def evaporation_rate(self, t_day):
        """Dynamic evaporation rate in mm/day"""
        if self.moisture > 700:
            base_evap = random.uniform(2, 12)
        else:
            base_evap = 0.0
        
        evap_max = 1.5
        evap = evap_max * max(self.temperature / 25, 0) * (1 - self.humidity / 100)
        
        diurnal_factor = max(0, np.sin(2 * np.pi * t_day))
        evap *= diurnal_factor
        
        return min(evap + base_evap, 12)

    def moisture_func(self, t_day, pump=False, alpha=0.01):
        """Update soil moisture with evaporation and gradual pump effect"""
        evap_mm_day = self.evaporation_rate( t_day)
        evap_per_sec = evap_mm_day / (24*60*60)
        moisture = self.moisture - evap_per_sec
        
        # Gradual pump tilt
        target_delta = 0.0
        if pump: target_delta += 50.0
        self.moist_tilt += alpha * (target_delta - self.moist_tilt)
        moisture += self.moist_tilt
        self.moisture=float(np.clip(moisture, 0, 1000))
        return float(np.clip(moisture, 0, 1000))

def environment_process(shared_mem, ready_event, time_acceleration:float|None=None):
    """
    Environment simulation loop.
    time_acceleration: number of simulated seconds per real second (time_acceleration 24 => 1 real hour = 1 simulated day)
    """
    time_acceleration =time_acceleration if time_acceleration else (365 * 24 * 3600) / (0.5 * 3600)

    env = EnvironmentState(latitude=45.0)
    
    alpha = 0.01  # tilt smoothing factor
    
    while True:
        # Accelerated simulation time
        t_sim = (time.time() - env.start_time) * time_acceleration
        t_days = env.start_day + (t_sim / (24*60*60))
        # Read controls
        fan = shared_mem.get('fan', False)
        heater = shared_mem.get('heater', False)
        pump = shared_mem.get('pump', False)
        humidifier = shared_mem.get('humidifier', False)
        dehumidifier = shared_mem.get('dehumidifier', False)
        shared_mem['temperature'] = round(env.temperature_func(t_days, fan, heater, alpha), 2)
        shared_mem['humidity'] = round(env.humidity_func(t_days, humidifier, dehumidifier, alpha), 2)
        shared_mem['moisture'] = round(env.moisture_func( t_days, pump, alpha), 2)
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
        stop_event = threading.Event()
        log_thread = threading.Thread(target=logger_loop, args=(log_queue, stop_event))
        log_thread.start()
        env_proc = mp.Process(target=environment_process,args=(shared_mem, ready_event),daemon=True)
        env_proc.start()
        print("Waiting for environment initialization...")
        ready_event.wait()  # Blocks until environment sets it
        print(f"Environment initialized")
        subscriber_proc = mp.Process(target=mqtt_to_mongodb_loop,args=(args.mongo_name, args.mongo_pass, args.mongo_cluster,log_queue, args.mqtt_host, args.mqtt_port,))
        subscriber_proc.start()
        
        sensors:List[Sensor]|None = []
        actuators:List[Actuator]|None=[]
        # for i in range(3):
        sensors.append(Sensor(f'Sensor_t{1}','temperature',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        sensors.append(Sensor(f'Sensor_h{1}','humidity',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        sensors.append(Sensor(f'Sensor_m{1}','moisture',shared_mem=shared_mem,location=math.degrees(math.asin(0.0))))
        
        actuators.append(Actuator(f'Actuator_t{1}','temperature',mode="heater",shared_mem=shared_mem,log_queue=log_queue))
        actuators.append(Actuator(f'Actuator_h{1}','humidity',mode="humidifier",shared_mem=shared_mem,log_queue=log_queue))
        actuators.append(Actuator(f'Actuator_m{1}','moisture',shared_mem=shared_mem,log_queue=log_queue))
        try:
            asyncio.run(gateway_loop(sensors,actuators, log_queue, mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port,poll_interval=2))
        except Exception as e:
            print(f"Gateway loop error: {e}")
            print("Exiting...")
            env_proc.terminate()
            subscriber_proc.terminate()
            env_proc.join()
            subscriber_proc.join()
            sensors.clear()
            actuators.clear()
            shared_mem.clear()
            log_queue.empty()
            log_queue.close()
            del(sensors)
            del(actuators)
    except KeyboardInterrupt:
        env_proc.terminate()
        subscriber_proc.terminate()
        env_proc.join()
        subscriber_proc.join()
        stop_event.set()
        sensors.clear()
        actuators.clear()
        shared_mem.clear()
        log_queue.empty()
        log_queue.close()
        del(sensors)
        del(actuators)
        print("Exiting...")


if __name__ == "__main__":
   main()

