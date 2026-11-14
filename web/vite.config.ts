import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const DEV_PORT = 3030;

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: DEV_PORT, strictPort: true },
  preview: { port: DEV_PORT },
});
