import socket
import json
from datetime import datetime

def run_server(ip="0.0.0.0", port=5000, expected_sensors=3):
    """
    UDP server that listens for JSON messages from multiple sensors.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ip, port))

    print(f"📡 Listening on {ip}:{port}")
    print(f"Expecting data from up to {expected_sensors} sensors.\n")
    print("Press Ctrl+C to stop.\n")

    received_sensors = set()

    try:
        while True:
            data, addr = sock.recvfrom(4096)  # Receive up to 4 KB per packet
            try:
                msg = json.loads(data.decode())
            except json.JSONDecodeError:
                print(f"⚠️ Invalid JSON from {addr}: {data}")
                continue

            sensor_id = msg.get("sensor_id", "unknown")
            temperature = msg.get("temperature_c")
            humidity = msg.get("humidity")
            timestamp = msg.get("timestamp")

            # Track sensors that have reported
            if sensor_id not in received_sensors:
                received_sensors.add(sensor_id)

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Sensor {sensor_id:<10} | "
                f"T={temperature:>5.2f}°C | H={humidity:>5.2f} | "
                f"from {addr[0]}"
            )

            # Optional: detect when all expected sensors have reported
            if len(received_sensors) >= expected_sensors:
                print(f"\n✅ All {expected_sensors} sensors are active!\n")
                expected_sensors = float("inf")  # print this only once
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    run_server(ip="0.0.0.0", port=5000, expected_sensors=3)
