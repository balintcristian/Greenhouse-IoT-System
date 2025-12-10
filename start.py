
import multiprocessing as mp

from multiprocessing import Manager
from typing import List,Literal

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import argparse
from urllib.parse import quote_plus
from urllib.parse import quote_plus
import json

import os,sys,signal,time
import csv
from enviroment.enviroment import enviroment_process
from sensor.sensor import sensor_process



def main():
    parser = argparse.ArgumentParser(description="MQTT Sensor Simulator")
    parser.add_argument("--sensor-id", type=str, required=True, help="sensor identifier, ex: sensor-t1")
    parser.add_argument("--sensor-type", type=str, choices=["temperature","humidity","moisture"], required=True, help="sensor type has to be: temperature, humidty or moisture")
    parser.add_argument("--host", type=str, help='Ip we\'re connecting to. Default "127.0.0.1"')
    parser.add_argument("--port", type=int, help="Port we're connecting on. Default is 5004")
    args = parser.parse_args()

    manager = Manager()
    enviroment_memory = manager.dict()
    env_ready = mp.Event()
    sen_ready = mp.Event()
    env_stop=mp.Event()
    sen_stop = mp.Event()

    env_process_ref = mp.Process(target=enviroment_process,args=(enviroment_memory, env_ready, env_stop))
    env_process_ref.start()
    print("Waiting for environment initialization...")
    env_ready.wait()
    print(f"Environment initialized")


    sensor_process_ref = mp.Process(target=sensor_process,args=(args.sensor_id,args.sensor_type,enviroment_memory, sen_ready, sen_stop,args.host,args.port))
    sensor_process_ref.start()
    print("Waiting for sensor initialization...")
    sen_ready.wait()
    print(f"Sensor initialized")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected! Shutting down...\n")
        env_stop.set()
        sen_stop.set()
        env_process_ref.join()
        sensor_process_ref.join()

if __name__ == "__main__":
   main()

