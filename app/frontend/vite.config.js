import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Собирает в ./dist — main.py (backend) отдаёт этот каталог как статику Cloud Run сервиса
// (единый контейнер: Flask API + собранный React).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
  },
});
