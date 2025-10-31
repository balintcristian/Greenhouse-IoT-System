import math
import random
import time
import json
import requests
from datetime import datetime
from pytz import timezone
import os

def simulate_sensor(
    base_temp:float=20.0,
    base_humidity:float=0.5,
    noise:float=0.02,
    delay:float=1.0,
    latitude:float=1.0,
    jitter:float=0.1,
    tz: str = "Europe/Bucharest",
):
    """
    Simulate a temperature + humidity sensor with:
    - Sinusoidal daily and seasonal variations
    - Latitude-based seasonal amplitude and phase
    - Random noise
    - Randomized delay between readings (±jitter seconds)
    """
    lat_factor = abs(latitude) / 90.0
    hemi_sign = 1 if latitude >= 0 else -1
    temp_season_amp = 10 * (0.5 + 0.5 * lat_factor)
    hum_season_amp = 0.1 * (0.5 + 0.5 * lat_factor)
    temp_daily_amp = 5 * (0.7 + 0.3 * lat_factor)

    while True:
        now = datetime.now(timezone(tz))
        hour = now.hour + now.minute / 60.0
        day_of_year = now.timetuple().tm_yday

        # Seasonal variation
        temp_season = temp_season_amp * math.sin(2 * math.pi * (day_of_year / 365.0) * hemi_sign)
        hum_season = -hum_season_amp * math.sin(2 * math.pi * (day_of_year / 365.0) * hemi_sign)

        # Daily variation
        temp_daily = temp_daily_amp * math.sin(2 * math.pi * ((hour - 15) / 24.0))
        hum_daily = 0.2 * math.sin(2 * math.pi * ((hour - 5) / 24.0))

        # Combine and add noise
        temperature = base_temp + temp_season + temp_daily + random.uniform(-noise * 10, noise * 10)
        humidity = base_humidity + hum_season + hum_daily - 0.01 * (temperature - base_temp)
        humidity += random.uniform(-noise, noise)
        humidity = max(0.0, min(1.0, humidity))

        yield {
            "timestamp": now.isoformat(),
            "latitude": latitude,
            "temperature_c": round(temperature, 2),
            "humidity": round(humidity, 3),
        }

        actual_delay = delay + random.uniform(-jitter, jitter)
        time.sleep(max(0.01, actual_delay))


def run_sensor(
    sensor_id: str,
    ip: str,
    port: int,
    delay: float,
    latitude: float,
    jitter: float ,
    tz: str,
):
    """
    Simulate a sensor that POSTs JSON data to a FastAPI server's /sensor-data endpoint.
    Only `sensor_id` is required. All other parameters are optional.
    """
    url = f"http://{ip}:{port}/sensor-data"
    print(f"\n🌡️ Sensor {sensor_id} sending POST data to {url}")
    print(f"Every ~{delay}s ±{jitter}s (latitude={latitude})\nPress Ctrl+C to stop.\n")

    try:
        for reading in simulate_sensor(delay=delay, latitude=latitude, jitter=jitter,tz=tz):
            reading["sensor_id"] = sensor_id
            response = requests.post(url, json=reading, timeout=5)
            print(f"→ Sent: {json.dumps(reading)} | Status: {response.status_code}")
    except KeyboardInterrupt:
        print("\n🛑 Sensor stopped.")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # import argparse
    # parser = argparse.ArgumentParser(description="Run sensor with configurable parameters")
    # parser.add_argument("--sensorId", type=str, required=True, help="Sensor id, mandatory")
    # parser.add_argument("--ip", type=str, default="127.0.0.1", help="Target server IP to send data")
    # parser.add_argument("--port", type=int, default=8000, help="Port to access server")
    # parser.add_argument("--delay", type=float, default=1.0, help="Delay between readings in seconds")
    # parser.add_argument("--latitude", type=float, default=0.0, help="Latitude for seasonal variations")
    # parser.add_argument("--jitter", type=float, default=0.1, help="Random delay jitter in seconds")
    # parser.add_argument("--tz", type=str, default="Europe/Bucharest", help="Timezone for timestamp")

    # args = parser.parse_args()
    # print(f"Running sensor with arguments: {args}")

    # run_sensor(
    #     sensor_id=args.sensorId,
    #     ip=args.ip,
    #     port=args.port,
    #     delay=args.delay,
    #     latitude=args.latitude,
    #     jitter=args.jitter,
    #     tz=args.tz
    # )
    sensor_id = os.getenv("SENSOR_ID", "SENSOR1")
    server_ip = os.getenv("SERVER_IP", "server")
    server_port = int(os.getenv("SERVER_PORT", 8000))
    delay = float(os.getenv("DELAY", 1.0))
    latitude = float(os.getenv("LATITUDE", 0.0))
    jitter = float(os.getenv("JITTER", 0.1))
    tz = os.getenv("TZ", "Europe/Bucharest")
    run_sensor(sensor_id, server_ip, server_port, delay, latitude, jitter, tz)
