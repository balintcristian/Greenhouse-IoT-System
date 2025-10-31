from fastapi import FastAPI, Request
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json

sensor_data_queue = asyncio.Queue()
log_lock = asyncio.Lock() 
LOG_FILE = "sensor_log.jsonl" 

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background processor
    processor_task = asyncio.create_task(process_sensor_data())
    print("✅ Background processor started.")
    yield
    # Stop processor on shutdown
    processor_task.cancel()
    print("🛑 Background processor stopped.")

app = FastAPI(lifespan=lifespan)

@app.post("/sensor-data")
async def receive_sensor_data(request: Request):
    data = await request.json()
    # Add timestamp for logging
    data["timestamp"] = datetime.utcnow().isoformat()
    await sensor_data_queue.put(data)
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
def append_to_file(line: str):
    """Runs in a thread pool to perform blocking I/O safely."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
        

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
