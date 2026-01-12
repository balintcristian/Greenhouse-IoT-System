import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export default function HumidityDashboard({ APIEndpoint }) {
  let navigate = useNavigate();
  const [sensorIds, setSensorIds] = useState([]);
  const [dataMap, setDataMap] = useState({});
  const [loading, setLoading] = useState(false);
  console.log(`${APIEndpoint}/sensors/humidity/`);
  const fetchSensorIds = async () => {
    try {
      const res = await fetch(`${APIEndpoint}/sensors/humidity/`);
      const json = await res.json();
      console.log(json);

      if (Array.isArray(json)) {
        // Extract unique sensor IDs
        const uniqueIds = [...new Set(json.map((item) => item.sensor_id))];
        setSensorIds(uniqueIds);
      } else {
        console.error("Sensor IDs response is not an array:", json);
      }
    } catch (err) {
      console.error("Failed to fetch sensor IDs:", err);
    }
  };

  const fetchSensorData = async () => {
    if (sensorIds.length === 0) return;
    setLoading(true);
    try {
      const results = await Promise.all(
        sensorIds.map(async (id) => {
          try {
            const res = await fetch(`${APIEndpoint}/sensors/humidity/${id}`);
            const json = await res.json();
            return Array.isArray(json) ? json : [];
          } catch (err) {
            console.error(`Failed to fetch data for sensor ${id}:`, err);
            return [];
          }
        })
      );

      setDataMap((prev) => {
        const newMap = { ...prev };
        results.forEach((sensorData) => {
          if (!Array.isArray(sensorData)) return;
          sensorData.forEach(({ sensor_id, value, time }) => {
            if (!sensor_id || value == null || !time) return;
            if (!newMap[sensor_id]) newMap[sensor_id] = [];
            if (!newMap[sensor_id].some((pt) => pt.time === time)) {
              newMap[sensor_id].push({ time, value });
            }
          });
        });
        return newMap;
      });
    } catch (err) {
      console.error("Failed to fetch sensor data:", err);
    }
    setLoading(false);
  };

  const mergedData = useMemo(() => {
    const allPoints = {};
    Object.keys(dataMap).forEach((sensorId) => {
      dataMap[sensorId].forEach((pt) => {
        if (!pt.time || pt.value == null) return;
        if (!allPoints[pt.time]) allPoints[pt.time] = { time: pt.time };
        allPoints[pt.time][sensorId] = pt.value;
      });
    });
    return Object.values(allPoints).sort((a, b) => new Date(a.time) - new Date(b.time));
  }, [dataMap]);

  useEffect(() => {
    fetchSensorIds();
  }, []);

  useEffect(() => {
    if (sensorIds.length === 0) return;
    fetchSensorData();
    const interval = setInterval(fetchSensorData, 2000);
    return () => clearInterval(interval);
  }, [sensorIds]);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-3xl font-bold">humidity Sensor Dashboard</h1>

      <div className="p-4 border rounded space-y-4">
        <button
          onClick={() => {
            navigate("/");
          }}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
        >
          Back
        </button>
        <button
          onClick={fetchSensorData}
          disabled={loading}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh Now"}
        </button>

        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={mergedData.length ? mergedData : [{ time: "", dummy: 0 }]}>
            <defs>
              {sensorIds.map((id, idx) => (
                <linearGradient id={`color-${id}`} key={id} x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={`hsl(${idx * 60}, 70%, 50%)`}
                    stopOpacity={0.8}
                  />
                  <stop
                    offset="95%"
                    stopColor={`hsl(${idx * 60}, 70%, 50%)`}
                    stopOpacity={0}
                  />
                </linearGradient>
              ))}
            </defs>

            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fontSize: 12 }} />
            <YAxis />
            <Tooltip />
            <Legend />

            {sensorIds.map((id, idx) => (
              <Area
                key={id}
                type="monotone"
                dataKey={id}
                stroke={`hsl(${idx * 60}, 70%, 50%)`}
                fillOpacity={0.3}
                fill={`url(#color-${id})`}
                strokeWidth={2}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
