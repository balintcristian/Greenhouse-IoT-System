from fastapi import FastAPI, Request
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import csv
import os

sensor_data_queue = asyncio.Queue()
log_lock = asyncio.Lock() 
LOG_FILE = "sensor_log.jsonl"
active_sensors = list()

EXPECTED_SENSORS = 3

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background processor
    processor_task = asyncio.create_task(process_sensor_data())
    print("✅ Background processor started.")
    yield # while FastAPI is running
    # Stop processor on shutdown
    processor_task.cancel()
    print("🛑 Background processor stopped.")

app = FastAPI(lifespan=lifespan)

@app.post("/sensor-data")
async def receive_sensor_data(request: Request):
    data = await request.json()
    data["timestamp"] = datetime.now().isoformat()
    await sensor_data_queue.put(data)

    sensor_id = data.get("sensor_id", "unknown")
    if sensor_id not in active_sensors:
        active_sensors.append(sensor_id)
        print(f"✅ New sensor detected: {sensor_id}")
        if len(active_sensors) == EXPECTED_SENSORS:
            print(f"🎉 All {EXPECTED_SENSORS} sensors are active!")

    temp = data.get("temperature_c")
    hum = data.get("humidity")
    lat = data.get("latitude")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sensor: {sensor_id:<10} T: {temp:>5.2f}°C H: {hum:>5.2f} Lat: {lat}")
    return {"status": "received"}


async def process_sensor_data():
    """Continuously consumes data from the queue and logs it to a file."""
    loop = asyncio.get_running_loop()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        while True:
            try:
                data = await sensor_data_queue.get()
                line = json.dumps(data) + "\n"
                await loop.run_in_executor(None, f.write, line)
                await loop.run_in_executor(None, f.flush)  # Ensure it's written
            except asyncio.CancelledError:
                print("Processor task cancelled.")
                break

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
