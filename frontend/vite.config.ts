import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: proxy các đường dẫn API sang backend FastAPI (mặc định :8000) nên không cần CORS và
// frontend luôn gọi đường dẫn tương đối. Production: backend tự phục vụ thư mục dist.
const target = process.env.BACKEND_URL ?? "http://localhost:8000";
const apiPaths = ["/health", "/catalog", "/documents", "/questions", "/users", "/quiz", "/evaluation"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target, changeOrigin: true }])),
  },
});
