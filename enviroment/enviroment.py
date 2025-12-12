import numpy as np
import math
import random
import time
from datetime import datetime
from multiprocessing import Manager
import multiprocessing as mp
from multiprocessing.synchronize import Event

class EnvironmentState:
    """Tracks environment variables and gradual control tilts"""
    def __init__(self, latitude=None):
        self.latitude = latitude if latitude is not None else math.degrees(math.asin(0.0))
        self.temperature = random.uniform(15, 20)
        self.humidity = 70.0
        self.moisture = random.uniform(300, 600)

        self.time = datetime.now().isoformat()
        self.start_time = time.time()
        self.start_day = 90

        # Gradual control tilts
        self.temp_tilt = 0.0
        self.hum_tilt = 0.0
        self.moist_tilt = 0.0  # NO LONGER unbounded

    # ----------------------------------------------------
    # KEEP EXACTLY YOUR TEMPERATURE MODEL
    # ----------------------------------------------------
    def temperature_func(self, t_days, fan=False, heater=False, alpha=0.05, thermal_inertia=0.1):
        lat_norm = abs(self.latitude) / 90.0

        BASE_TEMP = 27 - 32 * lat_norm
        A_seasonal = 3 + 20 * lat_norm
        seasonal = A_seasonal * np.sin(2 * np.pi * (t_days / 365 - 0.25))

        A_daily = 8 - 6 * lat_norm
        daily = A_daily * np.sin(2 * np.pi * (t_days % 1) - np.pi/2)

        years_passed = (time.time() - self.start_time) / (365*24*3600)
        noise_std = 0.3 + 0.02 * years_passed
        noise = np.random.normal(0, noise_std)

        temp = BASE_TEMP + seasonal + daily + noise

        # Tilt
        target_delta = 0
        if fan: target_delta -= 3
        if heater: target_delta += 3

        self.temp_tilt += alpha * (target_delta - self.temp_tilt)
        temp += self.temp_tilt

        # Inertia smoothing
        temp = self.temperature + thermal_inertia * (temp - self.temperature)

        # Clamp
        temp = max(min(temp, 50), -20)
        self.temperature = temp
        return temp

    # ----------------------------------------------------
    # HUMIDITY MODEL — CLEANED UP
    # ----------------------------------------------------
    def humidity_func(self, t_days, humidifier=False, dehumidifier=False, alpha=0.01):
        base_hum = 70 - 0.6 * max(self.temperature, 0)

        daily = 5 * np.sin(2 * np.pi * (t_days % 1))
        moisture_effect = (self.moisture - 500) / 250

        hum = base_hum + daily + moisture_effect
        hum += np.random.normal(0, 2.5)

        # Tilt
        target_delta = 0
        if humidifier: target_delta += 10
        if dehumidifier: target_delta -= 10

        self.hum_tilt += alpha * (target_delta - self.hum_tilt)
        hum += self.hum_tilt

        hum = float(np.clip(hum, 0, 100))
        self.humidity = hum
        return hum

    # ----------------------------------------------------
    # EVAPORATION — REALISTIC SCALING
    # ----------------------------------------------------
    def evaporation_rate(self, t_day):
        """Dynamic evaporation in mm/day with realistic baseline and diurnal cycle."""
        if self.moisture > 700:
            base_evap = random.uniform(1.0, 3.0)
        elif self.moisture > 400:
            base_evap = random.uniform(0.2, 0.8)
        else:
            base_evap = 0.05

        evap = max(self.temperature - 10, 0) * (1 - self.humidity / 100) * 0.1
        diurnal = 0.3 + 0.7 * max(0, np.sin(2 * np.pi * (t_day % 1)))
        evap *= diurnal
        evap += np.random.normal(0, 0.05)
        return float(max(base_evap + evap, 0.01))


    def moisture_func(self, t_day, pump=False, alpha=0.02,
                    sensitivity_mm_to_units=30.0,
                    pump_flow_units_per_sec=5.0):
        """
        Robust moisture update using actual simulated dt.
        - sensitivity_mm_to_units: how many 'moisture units' correspond to 1 mm/day lost (tunable).
        - pump_flow_units_per_sec: when pump ON, how many units/sec are added (tunable).
        - alpha: smoothing factor for a small gradual pump tilt (kept optional).
        """

        # Initialize last_update_time on first call
        now_real = time.time()
        if not hasattr(self, "_last_update_time"):
            self._last_update_time = now_real
            # small no-op to avoid huge dt on first call
            dt_real = 1.0
        else:
            dt_real = max(0.0001, now_real - self._last_update_time)

        # If you use time_acceleration somewhere else (t_sim), compute simulated dt:
        # If env loop computes t_sim = (time.time() - start_time) * time_acceleration,
        # then dt_sim = dt_real * time_acceleration.
        # For portability we compute dt_sim if self has time_acceleration attribute; else assume 1:1.
        time_accel = getattr(self, "time_acceleration", 1.0)
        dt_sim = dt_real * time_accel  # seconds of simulated time that passed

        # convert mm/day → mm per simulated second
        evap_mm_day = self.evaporation_rate(t_day)
        evap_mm_per_simsec = evap_mm_day / 86400.0
        # mm lost this update (simulated seconds elapsed)
        evap_mm_this_step = evap_mm_per_simsec * dt_sim

        # Convert to 'moisture units' via sensitivity parameter:
        evap_units = evap_mm_this_step * sensitivity_mm_to_units

        # Apply evap loss
        moisture = self.moisture - evap_units

        # Pump: treat as a flow (units/sec) multiplied by simulated dt
        target_pump_flow = pump_flow_units_per_sec if pump else 0.0
        # optional smoothing of pump flow (gentle actuator inertia)
        if not hasattr(self, "_pump_flow_tilt"):
            self._pump_flow_tilt = target_pump_flow
        self._pump_flow_tilt += alpha * (target_pump_flow - self._pump_flow_tilt)

        pump_added = self._pump_flow_tilt * dt_sim
        moisture += pump_added

        # small stochastic fluctuation so it's never perfectly constant
        moisture += np.random.normal(0, 0.005 * max(1.0, abs(moisture) / 100.0))

        # clamp & store dt
        moisture = float(np.clip(moisture, 0.0, 1000.0))
        self.moisture = moisture
        self._last_update_time = now_real
        return moisture


# ---------------------------------------------------------
# IMPROVED ENVIRONMENT LOOP (same memory interaction)
# ---------------------------------------------------------
def enviroment_process(enviroment_memory, ready_event: Event, stop_event: Event, time_acceleration: float | None = None):

    env = EnvironmentState(latitude=45.0)
    ready_event.set()

    if not time_acceleration:
        time_acceleration = (365 * 24 * 3600) / (0.5 * 3600)

    alpha = 0.01
    first = True

    try:
        while not stop_event.is_set():

            t_sim = (time.time() - env.start_time) * time_acceleration
            t_days = env.start_day + t_sim / 86400

            # Read controls
            fan = enviroment_memory.get('fan', False)
            heater = enviroment_memory.get('heater', False)
            pump = enviroment_memory.get('pump', False)
            humidifier = enviroment_memory.get('humidifier', False)
            dehumidifier = enviroment_memory.get('dehumidifier', False)

            # Write to shared memory (unchanged)
            enviroment_memory['temperature'] = round(env.temperature_func(t_days, fan, heater, alpha), 2)
            enviroment_memory['humidity'] = round(env.humidity_func(t_days, humidifier, dehumidifier, alpha), 2)
            enviroment_memory['moisture'] = round(env.moisture_func(t_days, pump, alpha), 2)
            enviroment_memory['time'] = datetime.now().isoformat()

            if first:
                ready_event.set()
                first = False

            time.sleep(1)

    except KeyboardInterrupt:
        print("Environment process interrupted")