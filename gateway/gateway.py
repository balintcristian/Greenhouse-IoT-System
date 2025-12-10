from fastapi import FastAPI
from typing import List
from pydantic import BaseModel
import datetime
import asyncio
import uvicorn
import json
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    tcp_task = asyncio.create_task(run_tcp_server())
    print("TCP server task started")
    yield
    tcp_task.cancel()
    print("TCP server task stopped")


app = FastAPI(lifespan=lifespan)

class Reading(BaseModel):
    sensor_id:int
    sensor_type:str
    value:str
    time:datetime.datetime
    
sensor_data:List[Reading] = []



sensor_data = []  # shared memory between TCP + HTTP


async def handle_tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    print(f"Client connected: {addr}")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break 
            try:
                data = json.loads(line.decode().strip())
                reading:Reading = Reading(**data)
                sensor_data.append(reading)
                print("Received:", data)
            except Exception as e:
                print("Error parsing:", e)

    finally:
        writer.close()
        await writer.wait_closed()
        print(f"Client disconnected: {addr}")

@app.get("/")
async def get_data():
    return sensor_data[-50:]  # last 50 readings

@app.post("/add")
async def add_data(item: Reading|List[Reading]):
    if isinstance(item,Reading):
        sensor_data.append(item)
    else:
        for obj in item:
            sensor_data.append(obj)
    return {"status": "ok"}


@app.get("/readings/{sensor_type}/{sensor_id}")
def read_item(sensor_type:str,sensor_id:int):
    results:List[Reading]=[]
    for reading in sensor_data:
        if reading.sensor_type==sensor_type and reading.sensor_id==sensor_id:
            results.append(reading)
    return results


async def run_tcp_server(host="127.0.0.1", port=5004):
    server = await asyncio.start_server(handle_tcp, host, port)
    print(f"TCP server listening on {host}:{port}")

    async with server:
        await server.serve_forever()

def start_fastapi(host="127.0.0.1", port=8000):
    uvicorn.run(
        "main:app",           # module:app
        host=host,
        port=port,
        reload=False,         # optional
        workers=1,            # must be 1 for asyncio tasks
        log_level="info"
    )


if __name__ == "__main__":
    start_fastapi(port=8080)   # choose your arguments here

    
