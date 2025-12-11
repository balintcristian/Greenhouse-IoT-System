import multiprocessing as mp
from multiprocessing import Manager
from typing import Dict
from enviroment.enviroment import enviroment_process
from sensor.sensor import sensor_process


def main():
    manager = Manager()
    enviroment_memory = manager.dict()
    env_ready = mp.Event()
    env_stop = mp.Event()

    # Start environment
    env_process_ref = mp.Process(target=enviroment_process, args=(enviroment_memory, env_ready, env_stop))
    env_process_ref.start()
    print("Waiting for environment initialization...")
    env_ready.wait()
    print("Environment initialized")
    sensors: Dict[str, Dict] = {}
    HELP_TEXT = """
    Available Commands:
    add <sensor_id> <sensor_type> <host> <port>     - Start a new sensor process
    remove <sensor_id>                              - Stop and remove a sensor
    restart <sensor_id>                             - Restart a sensor
    list                                            - List all active sensors
    help                                            - Show this help message
    quit / exit                                     - Stop everything and exit

    Valid sensor types: temperature, humidity, moisture
    """
    try:
        print(HELP_TEXT)
        while True:
            cmd = input("Commander> ").strip().lower()
            if cmd == "help":
                print(HELP_TEXT)
            elif cmd.startswith("add"):
                invalid=False
                try:
                    VALID_TYPES = ("temperature", "humidity", "moisture")
                    if len(cmd.split())<4:
                        _, sensor_id, sensor_type=cmd.split()
                        host="192.168.0.38"
                        port=8883
                    else:
                         _, sensor_id, sensor_type,host,port = cmd.split()
                         if len(host.split("."))>4:
                            print("Ip length is wrong!")
                            invalid=True
                         if not all(c.isdigit() for c in port):
                            invalid = True   
                            print("Port is not an integer?")
                except ValueError:
                    print("Usage: add <sensor_id!> <sensor_type!> <host> <port>")
                    continue
                if sensor_id in sensors:
                    print(f"{sensor_id} already exists!")
                    continue
                if sensor_type not in VALID_TYPES:
                    print(f"{sensor_id} Wrong sensor type!")
                    print(f"Valid types:{VALID_TYPES}")
                    continue
                if invalid:
                    continue
                ready_event = mp.Event()
                stop_event = mp.Event()
                p = mp.Process(target=sensor_process, args=(sensor_id, sensor_type, enviroment_memory, ready_event, stop_event,host,int(port)))
                p.start()
                ready_event.wait()
                sensors[sensor_id] = {"process": p, "stop_event": stop_event, "type": sensor_type, "host":host,"port":port}
                print(f"Sensor {sensor_id} ({sensor_type}) added and running")

            elif cmd.startswith("remove"):
                _, sensor_id = cmd.split()
                if sensor_id not in sensors:
                    print(f"{sensor_id} not found!")
                    continue
                sensors[sensor_id]["stop_event"].set()
                sensors[sensor_id]["process"].join()
                del sensors[sensor_id]
                print(f"Sensor {sensor_id} removed")

            elif cmd.startswith("restart") and not cmd.endswith(""):
                _, sensor_id = cmd.split()
                if sensor_id not in sensors:
                    print(f"{sensor_id} not found!")
                    continue
                info = sensors[sensor_id]
                host = info["host"]
                port = info["port"]
                sensor_type = info["type"]

                info["stop_event"].set()
                info["process"].join()

                ready_event = mp.Event()
                stop_event = mp.Event()
                p = mp.Process(target=sensor_process, args=(sensor_id,sensor_type, enviroment_memory, ready_event, stop_event, host, port))
                p.start()
                ready_event.wait()
                sensors[sensor_id] = {"process": p, "stop_event": stop_event, "type":sensor_type}
                print(f"Sensor {sensor_id} restarted")

            elif cmd == "list":
                print("Active sensors:")
                for id, info in sensors.items():
                    print(f"  {id} ({info['type']})")

            elif cmd in ("quit", "exit"):
                print("Shutting down all sensors and environment...")
                break

            elif cmd in ("help"):
                print(HELP_TEXT)
            else:
                continue

    except KeyboardInterrupt:
        print("\nCtrl+C detected! Shutting down...")

    for info in sensors.values():
        info["stop_event"].set()
        info["process"].join()

    env_stop.set()
    env_process_ref.join()
    print("Shutdown complete")

if __name__ == "__main__":
    main()
