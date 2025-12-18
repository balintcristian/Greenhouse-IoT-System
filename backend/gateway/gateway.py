from typing import Any
from collections import deque
import asyncio
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from pymongo import AsyncMongoClient
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import logging

log = logging.getLogger("uvicorn")
log.setLevel(logging.DEBUG)

col_temperature: Any
col_humidity: Any
col_moisture: Any

MONGO_URI = "mongodb+srv://gateway:Aq5GN3BRurusVlJ7@cluster0.daspxne.mongodb.net/?appName=Cluster0"
mongo_client = None

MQTT_BROKER = "192.168.0.38"
MQTT_PORT = 8883

class Reading(BaseModel):
    sensor_id: str
    sensor_type: str
    value: float
    time: datetime


async def queue_consumer(app: FastAPI):
    """Consume readings from the async queue and push into the correct buffer."""
    while True:
        reading: Reading = await app.state.data_queue.get()
        try:
            if reading.sensor_type == "temperature":
                app.state.temperature_data.append(reading)
            elif reading.sensor_type == "humidity":
                app.state.humidity_data.append(reading)
            elif reading.sensor_type == "moisture":
                app.state.moisture_data.append(reading)
        finally:
            app.state.data_queue.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic using async context manager."""
    global mongo_client, col_temperature, col_humidity, col_moisture,MONGO_URI
    existing=None
    try:
        mongo_client= AsyncMongoClient(MONGO_URI)
        db = mongo_client["sensors"]
        col_temperature = db["temperature"]
        col_humidity = db["humidity"]
        col_moisture = db["moisture"]
    except Exception as e:
        log.exception(e)
    try:
        existing = await db.list_collection_names()
    except Exception as e:
        log.exception(e)

    app.state.temperature_data = deque(maxlen=100)
    app.state.humidity_data = deque(maxlen=100)
    app.state.moisture_data = deque(maxlen=100)
    app.state.data_queue = asyncio.Queue()


    for name in ["temperature", "humidity", "moisture"]:
        if existing!=None and name not in existing:
            await db.create_collection(name)
            print("Created collection:", name)

    loop = asyncio.get_running_loop()
    consumer_task = asyncio.create_task(queue_consumer(app))
    mqtt_task = asyncio.create_task(run_mqtt_client(loop,app))
    try:
        yield
    finally:
        mqtt_task.cancel()
        consumer_task.cancel()
        if mongo_client !=None:
            await mongo_client.close()
        print("App shutting down...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=["*"],  # OR change to your frontend IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])
@app.get("/")
def HomeData1(request: Request):
    state = request.app.state
    return list(state.temperature_data)+list(state.humidity_data)+list(state.moisture_data)

@app.get("/sensors")
def HomeData(request: Request):
    state = request.app.state
    return list(state.temperature_data)+list(state.humidity_data)+list(state.moisture_data)


@app.get("/sensors/{sensor_type}")
async def get_sensor_type_data(sensor_type: str,request: Request):
    state = request.app.state
    buffer_map = {
        "temperature": state.temperature_data,
        "humidity": state.humidity_data,
        "moisture": state.moisture_data
    }
    buffer = buffer_map.get(sensor_type.lower())
    if buffer is None:
        return {"error": "Invalid sensor type"}
    return list(buffer)
@app.get("/sensors/{sensor_type}/{sensor_id}")
async def get_sensor_id_data(sensor_type: str,sensor_id:str,request: Request):
    state = request.app.state
    buffer_map = {
        "temperature": state.temperature_data,
        "humidity": state.humidity_data,
        "moisture": state.moisture_data
    }
    buffer = buffer_map.get(sensor_type.lower())
    if buffer is None:
        return {"error": "Invalid sensor type"}
    return [r for r in buffer if r.sensor_id == sensor_id]


@app.post("/add")
async def add_data(item: Reading | List[Reading],request:Request):
    state = request.app.state
    """Add a new reading or list of readings manually (for HTTP clients)."""
    items = item if isinstance(item, list) else [item]
    for r in items:
        await state.data_queue.put(r)
    return {"status": "ok"}

async def run_mqtt_client(loop,app):
    """Connect to MQTT broker and push messages into async queue."""

    async def save_to_mongo(reading: Reading):
        if reading.sensor_type == "temperature":
            await col_temperature.insert_one(reading.model_dump())
        elif reading.sensor_type == "humidity":
            await col_humidity.insert_one(reading.model_dump())
        elif reading.sensor_type == "moisture":
            await col_moisture.insert_one(reading.model_dump())
            
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT broker!")
            client.subscribe("sensors/#")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            reading = Reading(**data)
            asyncio.run_coroutine_threadsafe(save_to_mongo(reading), loop)
            asyncio.run_coroutine_threadsafe(app.state.data_queue.put(reading), loop)
        except Exception as e:
            print(f"Error parsing MQTT message: {e}")

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION1,client_id="gateway",clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(host=MQTT_BROKER, port=MQTT_PORT, keepalive=60)
    await loop.run_in_executor(None, client.loop_forever)

if __name__ == "__main__":
    uvicorn.run("gateway:app", host="192.168.0.38",port=8000, reload=False, workers=1, log_level="info")

