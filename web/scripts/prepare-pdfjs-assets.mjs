import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDirectory, "..");
const pdfjsRoot = path.join(webRoot, "node_modules", "pdfjs-dist");
const publicRoot = path.join(webRoot, "public", "pdfjs");

for (const directory of ["cmaps", "standard_fonts", "wasm"]) {
  const source = path.join(pdfjsRoot, directory);
  const target = path.join(publicRoot, directory);
  if (!fs.existsSync(source)) {
    console.error(`[pdfjs assets] Missing audited dependency directory: ${source}`);
    process.exit(1);
  }
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true });
}

const workerSource = path.join(pdfjsRoot, "build", "pdf.worker.min.mjs");
const workerTarget = path.join(publicRoot, "pdf.worker.min.js");
if (!fs.existsSync(workerSource)) {
  console.error(`[pdfjs assets] Missing audited worker module: ${workerSource}`);
  process.exit(1);
}
fs.copyFileSync(workerSource, workerTarget);

console.log("[pdfjs assets] Prepared local worker, CMaps, standard fonts and WASM resources.");
