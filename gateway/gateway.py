from collections import deque
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
import datetime
import uvicorn
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import asyncio
from contextlib import asynccontextmanager
# OR for new PyMongo Async:
from pymongo import AsyncMongoClient

from typing import Any

col_temperature: Any
col_humidity: Any
col_moisture: Any

MONGO_URI = "mongodb+srv://gateway:<password>@cluster0.mdey7y7.mongodb.net/?appName=Cluster0"
mongo_client = None

MQTT_BROKER = "192.168.0.38"
MQTT_PORT = 8883


# Buffers per sensor type, storing last 100 readings
temperature_data = deque(maxlen=100)
humidity_data = deque(maxlen=100)
moisture_data = deque(maxlen=100)

# Async queue for thread-safe MQTT processing
data_queue: asyncio.Queue = asyncio.Queue()

class Reading(BaseModel):
    sensor_id: str
    sensor_type: str  # 'temperature', 'humidity', 'moisture'
    value: float
    time: str


async def queue_consumer():
    """Consume readings from the async queue and push into the correct buffer."""
    while True:
        reading: Reading = await data_queue.get()
        if reading.sensor_type == "temperature":
            temperature_data.append(reading)
        elif reading.sensor_type == "humidity":
            humidity_data.append(reading)
        elif reading.sensor_type == "moisture":
            moisture_data.append(reading)
        await asyncio.sleep(0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic using async context manager."""
    global mongo_client, col_temperature, col_humidity, col_moisture,MONGO_URI
    mongo_client = AsyncMongoClient(MONGO_URI)
    db = mongo_client["sensors"]
    col_temperature = db["temperature"]
    col_humidity = db["humidity"]
    col_moisture = db["moisture"]
    existing = await db.list_collection_names()
    for name in ["temperature", "humidity", "moisture"]:
        if name not in existing:
            await db.create_collection(name)
            print("Created collection:", name)

    loop = asyncio.get_running_loop()
    consumer_task = asyncio.create_task(queue_consumer())
    mqtt_task = asyncio.create_task(run_mqtt_client(loop))
    try:
        yield
    finally:
        mqtt_task.cancel()
        consumer_task.cancel()
        await mongo_client.close()
        await asyncio.sleep(0)
        print("App shutting down...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=["*"],  # OR change to your frontend IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])
@app.get("/")
def HomeData1():
    return list(temperature_data+humidity_data+moisture_data)

@app.get("/sensors")
def HomeData():
    return list(temperature_data+humidity_data+moisture_data)

@app.get("/sensors/{sensor_type}")
async def get_sensor_type_data(sensor_type: str):
    buffer_map = {
        "temperature": temperature_data,
        "humidity": humidity_data,
        "moisture": moisture_data
    }
    buffer = buffer_map.get(sensor_type.lower())
    if buffer is None:
        return {"error": "Invalid sensor type"}
    return list(buffer)
@app.get("/sensors/{sensor_type}/{sensor_id}")
async def get_sensor_id_data(sensor_type: str,sensor_id:str):

    buffer_map = {
        "temperature": temperature_data,
        "humidity": humidity_data,
        "moisture": moisture_data
    }
    buffer = buffer_map.get(sensor_type.lower())
    if buffer is None:
        return {"error": "Invalid sensor type"}
    return [r for r in buffer if r.sensor_id == sensor_id]


@app.post("/add")
async def add_data(item: Reading | List[Reading]):
    """Add a new reading or list of readings manually (for HTTP clients)."""
    items = item if isinstance(item, list) else [item]
    for r in items:
        await data_queue.put(r)
    return {"status": "ok"}

async def run_mqtt_client(loop):
    """Connect to MQTT broker and push messages into async queue."""

    async def save_to_mongo(reading: Reading):
        if reading.sensor_type == "temperature":
            await col_temperature.insert_one(reading.dict())
        elif reading.sensor_type == "humidity":
            await col_humidity.insert_one(reading.dict())
        elif reading.sensor_type == "moisture":
            await col_moisture.insert_one(reading.dict())
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
            asyncio.run_coroutine_threadsafe(data_queue.put(reading), loop)
        except Exception as e:
            print(f"Error parsing MQTT message: {e}")

    client = mqtt.Client(CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    await loop.run_in_executor(None, client.loop_forever)

def start_fastapi(host="192.168.0.38", port=8000):
    uvicorn.run("gateway:app", host=host, port=port, reload=False, workers=1, log_level="info")

def main():
    start_fastapi(host="192.168.0.38",port=8000)

if __name__ == "__main__":
    main()
