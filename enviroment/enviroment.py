
import numpy as np
import math
import random
import time
from datetime import datetime
from multiprocessing import Manager
import multiprocessing as mp

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
        A_daily = 8 - 6 * lat_norm  
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
    
def environment_process(enviroment_memory, ready_event, stop_event, time_acceleration:float|None=None):
    """
    Environment simulation loop.
    time_acceleration: number of simulated seconds per real second (time_acceleration 24 => 1 real hour = 1 simulated day)
    """
    time_acceleration =time_acceleration if time_acceleration else (365 * 24 * 3600) / (0.5 * 3600)

    env = EnvironmentState(latitude=45.0)
    
    alpha = 0.01  # tilt smoothing factor
    
    while not stop_event:
        # Accelerated simulation time
        t_sim = (time.time() - env.start_time) * time_acceleration
        t_days = env.start_day + (t_sim / (24*60*60))
        # Read controls
        fan = enviroment_memory.get('fan', False)
        heater = enviroment_memory.get('heater', False)
        pump = enviroment_memory.get('pump', False)
        humidifier = enviroment_memory.get('humidifier', False)
        dehumidifier = enviroment_memory.get('dehumidifier', False)
        enviroment_memory['temperature'] = round(env.temperature_func(t_days, fan, heater, alpha), 2)
        enviroment_memory['humidity'] = round(env.humidity_func(t_days, humidifier, dehumidifier, alpha), 2)
        enviroment_memory['moisture'] = round(env.moisture_func( t_days, pump, alpha), 2)
        enviroment_memory['time'] = datetime.now().isoformat()
        ready_event.set()
        time.sleep(1)
