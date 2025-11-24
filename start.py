import time
import random
from datetime import datetime
import multiprocessing as mp
import numpy as np
import asyncio

def temperature_func(   mean_temp=15,      # average temperature in °C
                        amplitude=10,      # seasonal amplitude
                        phase_shift=0,     # to adjust peak summer day
                        noise_std=2,       # standard deviation of random noise
                    )->float:
    """
    Returns the current temperature at the current system time.
    Parameters:
        mean_temp (float): Average temperature.
        amplitude (float): Seasonal amplitude.
        phase_shift (float): Days to shift the seasonal peak.
        noise_std (float): Standard deviation of random noise.
    Returns:
        float: Temperature in °C.
    """
    # Get current time in seconds since epoch
    now_seconds = time.time()
    
    # Convert seconds to fractional days
    t_days = now_seconds / (24 * 60 * 60)
    
    # Seasonal component (1 year = 365 days)
    seasonal = amplitude * np.sin(2 * np.pi * (t_days + phase_shift) / 365)
    
    # Daily variation (24-hour cycle)
    daily = 2 * np.sin(2 * np.pi * t_days)
    
    # Small random noise
    noise = np.random.normal(0, noise_std)
    
    return mean_temp + seasonal + daily + noise


def moisture_func()->float:
    return random.uniform(300, 700)
def humidity_func()->float:
    return random.uniform(40, 60)

def environment_process(shared_mem):
    while True:
        shared_mem['temperature'] = temperature_func()
        shared_mem['humidity'] = round(humidity_func(),2)
        shared_mem['moisture'] = round(moisture_func(),2)
        shared_mem['time'] = datetime.now()
        print(shared_mem)
        print(shared_mem['temperature'])
        time.sleep(2)

class Sensor:
    VALID_TYPES = ("temperature", "humidity", "moisture")
    def __init__(self, sensor_id,sensor_type,shared_mem):
        if sensor_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid sensor_type: {sensor_type}\n Valid types:{self.VALID_TYPES}")
        self.sensor_id = sensor_id
        self.sensor_type=sensor_type
        self.shared_mem=shared_mem

    async def getValue(self):
        return self.shared_mem[self.sensor_type]
    
# # Async gateway function to poll all sensors
# async def gateway_loop(sensors, poll_interval=2):
#     while True:
#         tasks = [sensor.getValue() for sensor in sensors]
#         await asyncio.gather(*tasks)
#         await asyncio.sleep(poll_interval)

# if __name__ == "__main__":
#     num_sensors = 9

#     # Shared array for sensors
#     shared_mem = mp.Array('d', [0.0]*num_sensors)

#     # Start environment process
#     env_proc = mp.Process(target=environment_process, args=(shared_mem,), daemon=True)
#     env_proc.start()

#     # Create sensor objects
#     sensors = []
#     for i in range(3):
#         sensors.append(Sensor(f't{i}','temperature',shared_mem=shared_mem))
#         sensors.append(Sensor(f'h{i}','humidity',shared_mem=shared_mem))
#         sensors.append(Sensor(f'm{i}','moisture',shared_mem=shared_mem))

#     try:
#         asyncio.run(gateway_loop(sensors))
#     except KeyboardInterrupt:
#         print("Exiting...")