from fastapi import FastAPI

app = FastAPI()
sensor_data = []

@app.get("/")
async def get_data():
    return sensor_data[-50:]  # last 50 readings

@app.post("/add")
async def add_data(item: dict):
    sensor_data.append(item)
    print(item)
    return {"status": "ok"}
