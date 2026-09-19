import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDirectory, "..");
const patches = [
  {
    file: "server/static-file-cache.js",
    original: "relativePath: path.relative(base, batch[j]),",
    patched: 'relativePath: path.relative(base, batch[j]).split(path.sep).join("/"),',
    description: "production static asset paths",
  },
  {
    // Vinext 0.0.50's HTML redirect probe reads a property that its own
    // collectAppPageSearchParams() does not return. The actual page renderer
    // uses pageSearchParams. Keep both paths on that same request data.
    file: "entries/app-rsc-entry.js",
    original: "__collectAppPageSearchParams(searchParams).searchParamsObject,",
    patched: "__collectAppPageSearchParams(searchParams).pageSearchParams,",
    description: "request query parameters in server redirect probes",
  },
];

for (const { file, original, patched, description } of patches) {
  const target = path.join(webRoot, "node_modules/vinext/dist", file);
  if (!fs.existsSync(target)) throw new Error(`[vinext patch] Missing target: ${target}`);
  const source = fs.readFileSync(target, "utf8");
  if (source.includes(patched)) {
    console.log(`[vinext patch] Already corrected: ${description}.`);
    continue;
  }
  if (source.split(original).length !== 2) {
    throw new Error(`[vinext patch] Review changed upstream implementation before building: ${file}`);
  }
  fs.writeFileSync(target, source.replace(original, patched), "utf8");
  console.log(`[vinext patch] Corrected: ${description}.`);
}
