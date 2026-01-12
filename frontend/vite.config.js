import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import dns from "node:dns";

dns.setDefaultResultOrder("verbatim");

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      base: process.env.VITE_BASE_PATH || "/Greehouse-IoT-System/frontend",
    },
  },
});
