import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pyproject = readFileSync(
  resolve(__dirname, "../../pyproject.toml"),
  "utf-8",
);
const version = pyproject.match(/^version\s*=\s*"(.+)"/m)?.[1] ?? "0.0.0";
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || "/",
  define: {
    __MM_VERSION__: JSON.stringify(version),
  },
  server: { port: 9090 },
});
