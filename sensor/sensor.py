
import math,random,asyncio,json
from multiprocessing.synchronize import Event
from typing import List

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
        message = (json.dumps(self.enviroment_memory) + "\n").encode("utf-8")
        return message

    def __str__(self):
        return f"""Sensor - {self.sensor_id}:
        'sensor_id':'{self.sensor_id}'
        'sensor_type':'{self.sensor_type}'
        'latitude':'{self.latitude}'
        'locationalNoise':'{self.locTempNoise}'\n"""


def sensor_process(stop_event: Event, sensor_id, sensor_type, enviroment_memory, host="127.0.0.1", port=5004, numberOfSensor:int=1):
    sensors_list:List[Sensor]=[]
    async def async_worker():
        _, writer = await asyncio.open_connection(host, port)
        try:
            while not stop_event.is_set():
                tasks = [sensor.getValue() for sensor in sensors_list]
                readings = await asyncio.gather(*tasks)
                for reading in readings:
                    writer.write(reading)
                await writer.drain()
                await asyncio.sleep(1)
        finally:
            writer.close()
            await writer.wait_closed()
    
    if numberOfSensor>1:
        for i in range(numberOfSensor):
            sensors_list.append(Sensor(sensor_id=f"sensor_{sensor_type[0]}{i}",sensor_type=sensor_type,enviroment_memory=enviroment_memory))        
        asyncio.run(async_worker())
    else:
        sensors_list.append(Sensor(sensor_id=sensor_id,sensor_type=sensor_type,enviroment_memory=enviroment_memory))
        asyncio.run(async_worker())
        



