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
  {
    // Backport https://github.com/cloudflare/vinext/pull/2929 to 0.0.50.
    // LAN HTTP lacks SubtleCrypto; the existing server already accepts this
    // legacy cache key. Secure contexts retain the original SHA-256 key.
    file: "server/app-rsc-cache-busting.js",
    original: '\tconst digest = await globalThis.crypto.subtle.digest("SHA-256", textEncoder.encode(input));',
    patched: '\tconst subtle = globalThis.crypto?.subtle;\n\tif (!subtle) return fnv1a64(input);\n\tconst digest = await subtle.digest("SHA-256", textEncoder.encode(input));',
    description: "RSC cache keys in HTTP LAN browser contexts",
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
