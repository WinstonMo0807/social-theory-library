import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDirectory, "..");
const target = path.join(
  webRoot,
  "node_modules",
  "vinext",
  "dist",
  "server",
  "static-file-cache.js",
);

const original = "relativePath: path.relative(base, batch[j]),";
const patched =
  'relativePath: path.relative(base, batch[j]).split(path.sep).join("/"),';

if (!fs.existsSync(target)) {
  console.error(`[vinext patch] Missing target: ${target}`);
  process.exit(1);
}

const source = fs.readFileSync(target, "utf8");

if (source.includes(patched)) {
  console.log("[vinext patch] Static asset paths are already normalized.");
  process.exit(0);
}

if (!source.includes(original)) {
  console.error(
    "[vinext patch] The installed Vinext version no longer matches the audited source. Review the upstream implementation before building.",
  );
  process.exit(1);
}

fs.writeFileSync(target, source.replace(original, patched), "utf8");
console.log("[vinext patch] Normalized production static asset paths.");
