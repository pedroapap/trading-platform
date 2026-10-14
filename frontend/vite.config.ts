import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // The browser talks to one origin; the API needs no CORS.
    proxy: { "/api": process.env.API_URL ?? "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Times are shown in the browser's time zone; tests pin it.
    env: { TZ: "UTC" },
  },
});
