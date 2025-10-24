import math
import random
import socket
import sys
import time
import json
from datetime import datetime

def simulate_sensor(base_temp=20.0, base_humidity=0.5, noise=0.02, delay=1.0, latitude=1.0, jitter=0.1):
    """
    Simulate a temperature + humidity sensor with:
    - Sinusoidal daily and seasonal variations
    - Latitude-based season amplitude and phase
    - Random noise
    - Randomized delay between readings (±jitter seconds)
    """
    # Latitude effects
    lat_factor = abs(latitude) / 90.0
    hemi_sign = 1 if latitude >= 0 else -1
    temp_season_amp = 10 * (0.5 + 0.5 * lat_factor)
    hum_season_amp = 0.1 * (0.5 + 0.5 * lat_factor)
    temp_daily_amp = 5 * (0.7 + 0.3 * lat_factor)

    while True:
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        day_of_year = now.timetuple().tm_yday

        # Seasonal variation
        temp_season = temp_season_amp * math.sin(2 * math.pi * (day_of_year / 365.0) * hemi_sign)
        hum_season = -hum_season_amp * math.sin(2 * math.pi * (day_of_year / 365.0) * hemi_sign)

        # Daily variation
        temp_daily = temp_daily_amp * math.sin(2 * math.pi * ((hour - 15) / 24.0))
        hum_daily = 0.2 * math.sin(2 * math.pi * ((hour - 5) / 24.0))

        # Combine
        temperature = base_temp + temp_season + temp_daily + random.uniform(-noise*10, noise*10)
        humidity = base_humidity + hum_season + hum_daily - 0.01 * (temperature - base_temp)
        humidity += random.uniform(-noise, noise)
        humidity = max(0.0, min(1.0, humidity))

        yield {
            "timestamp": now.isoformat(),
            "latitude": latitude,
            "temperature_c": round(temperature, 2),
            "humidity": round(humidity, 3)
        }

        # Randomized delay
        actual_delay = delay + random.uniform(-jitter, jitter)
        if actual_delay < 0.01:  # prevent too small/negative delays
            actual_delay = 0.01
        time.sleep(actual_delay)


def run_sensor(sensor_id, ip="0.0.0.0", port=5000, delay=1.0, latitude=0.0, jitter=0.1):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("\nSensor started!\n")
    print("Press Ctrl+C to stop.\n")

    try:
        print(f"🌡️ Sensor {sensor_id} sending data to {ip}:{port} every ~{delay}s ±{jitter}s (lat={latitude})")
        for reading in simulate_sensor(delay=delay, latitude=latitude, jitter=jitter):
            reading["sensor_id"] = sensor_id
            msg = json.dumps(reading)
            sock.sendto(msg.encode(), (ip, port))
            print(f"Sent → {msg}")
    except KeyboardInterrupt:
        print("\n🛑 Sensor stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5, 6, 7):
        print("Usage: python sensor.py <sensor_id> <ip> <port> [delay_seconds] [latitude] [jitter_seconds]")
        sys.exit(1)

    sensor_id = sys.argv[1]
    ip = sys.argv[2]
    port = int(sys.argv[3])
    delay = float(sys.argv[4]) if len(sys.argv) >= 5 else 1.0
    latitude = float(sys.argv[5]) if len(sys.argv) >= 6 else 0.0
    jitter = float(sys.argv[6]) if len(sys.argv) == 7 else 0.1

    run_sensor(sensor_id, delay, latitude, jitter)
