import { defineConfig } from "vite";
import vinext from "vinext";

// Explicit opt-in local/LAN demo transport. The ordinary deployment is unchanged.
const endpoint = process.env.STL_DEMO_API_URL;
if (!endpoint || !/^http:\/\/(192\.168\.5\.6|127\.0\.0\.1):18091$/.test(endpoint)) {
  throw new Error("Set STL_DEMO_API_URL to the isolated candidate API, never the production endpoint.");
}
export default defineConfig({
  plugins: [vinext()],
  server: { host: "192.168.5.3", port: 5174, strictPort: true,
    proxy: { "/api": { target: endpoint, changeOrigin: false } } },
});
