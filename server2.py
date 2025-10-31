"""
async_web_mosquitto.py
An asyncio web server that connects to an external Mosquitto broker.

Endpoints:
  GET  /health
  GET  /sensors
  GET  /sensors/{id}
  POST /publish  -> publish to MQTT

Requires Mosquitto running (default tcp://localhost:1883)
"""

import asyncio
import json
import logging
from datetime import datetime
from aiohttp import web
from asyncio_mqtt import Client, MqttError

# --- CONFIGURATION ---
BROKER_HOST = "localhost"
BROKER_PORT = 1883
MQTT_TOPIC_SUBSCRIBE = "sensors/#"

# --- GLOBALS ---
SENSOR_STORE = {}
logger = logging.getLogger("mqtt_web")

# --- MQTT HANDLER TASK ---
async def mqtt_listener(stop_event: asyncio.Event):
    """Subscribe to sensors/# and store incoming messages."""
    while not stop_event.is_set():
        try:
            async with Client(BROKER_HOST, BROKER_PORT) as client:
                logger.info("Connected to Mosquitto at %s:%d", BROKER_HOST, BROKER_PORT)
                async with client.filtered_messages(MQTT_TOPIC_SUBSCRIBE) as messages:
                    await client.subscribe(MQTT_TOPIC_SUBSCRIBE)
                    async for msg in messages:
                        topic = msg.topic
                        payload = msg.payload.decode()
                        try:
                            data = json.loads(payload)
                        except Exception:
                            data = payload
                        parts = topic.split('/')
                        sensor_id = parts[1] if len(parts) > 1 else topic
                        SENSOR_STORE[sensor_id] = {
                            "topic": topic,
                            "payload": data,
                            "ts": datetime.utcnow().isoformat() + "Z",
                        }
                        logger.info("Sensor %s updated: %s", sensor_id, data)
        except MqttError as e:
            logger.warning("MQTT connection lost (%s), retrying in 5s", e)
            await asyncio.sleep(5)

# --- HTTP HANDLERS ---
async def health(request):
    return web.json_response({"status": "ok", "time": datetime.utcnow().isoformat() + "Z"})

async def get_all_sensors(request):
    data = [{"sensor_id": k, **v} for k, v in SENSOR_STORE.items()]
    return web.json_response({"count": len(data), "sensors": data})

async def get_sensor(request):
    sid = request.match_info["sensor_id"]
    if sid not in SENSOR_STORE:
        raise web.HTTPNotFound(text=json.dumps({"error": "sensor not found"}), content_type="application/json")
    return web.json_response({"sensor_id": sid, **SENSOR_STORE[sid]})

async def publish_endpoint(request):
    """Publish via Mosquitto"""
    try:
        body = await request.json()
        topic = body["topic"]
        payload = body["payload"]
        qos = int(body.get("qos", 0))
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid request"}), content_type="application/json")

    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)

    async with Client(BROKER_HOST, BROKER_PORT) as client:
        await client.publish(topic, payload.encode(), qos=qos)
    return web.json_response({"status": "published", "topic": topic})

# --- APP SETUP ---
async def init_app():
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/sensors", get_all_sensors)
    app.router.add_get("/sensors/{sensor_id}", get_sensor)
    app.router.add_post("/publish", publish_endpoint)
    return app

async def main():
    logging.basicConfig(level=logging.INFO)
    stop_event = asyncio.Event()

    # start MQTT listener
    mqtt_task = asyncio.create_task(mqtt_listener(stop_event))

    # start aiohttp web server
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("HTTP server running on http://0.0.0.0:8080")

    try:
        # run until cancelled (Ctrl+C)
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        stop_event.set()
        await mqtt_task
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
