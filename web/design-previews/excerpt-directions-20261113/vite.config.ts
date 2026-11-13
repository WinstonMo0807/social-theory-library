import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
const web = fileURLToPath(new URL("../../", import.meta.url));
export default defineConfig({ root:fileURLToPath(new URL(".",import.meta.url)), publicDir:`${web}/public`, plugins:[react()], resolve:{alias:{"@":web},dedupe:["react","react-dom"]}, server:{host:"0.0.0.0",port:18895,strictPort:true,fs:{allow:[web]}}, build:{outDir:"../../../tmp/excerpt-ui-20261113/demo-dist",emptyOutDir:false} });
