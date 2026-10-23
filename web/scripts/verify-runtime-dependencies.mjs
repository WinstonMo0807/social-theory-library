import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

// Read package metadata only; never load application or dependency code.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lockBytes = fs.readFileSync(path.join(root, "package-lock.json"));
const lock = JSON.parse(lockBytes);
const manifest = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const [major, minor, patch] = process.versions.node.split(".").map(Number);
const floor = { 22: [23, 4], 24: [22, 1], 26: [12, 1] }[major];
if (!floor || minor < floor[0] || (minor === floor[0] && patch < floor[1])) {
  throw Error(`Node ${process.versions.node} is outside the reviewed security baseline (22.23.4 / 24.22.1 / 26.12.1).`);
}
for (const field of ["dependencies", "devDependencies", "engines"]) {
  if (JSON.stringify(lock.packages[""][field]) !== JSON.stringify(manifest[field])) {
    throw Error(`package-lock.json does not match package.json: ${field}`);
  }
}
const targetPlatform = process.argv.includes("--linux") ? "linux" : process.platform;
const allowed = (values, target) => !values || (!values.includes(`!${target}`) && (values.every(value => value.startsWith("!")) || values.includes(target)));
let checked = 0;
for (const [relative, row] of Object.entries(lock.packages)) {
  if (!relative || row.dev || row.link || !allowed(row.os, targetPlatform) || !allowed(row.cpu, process.arch) || (targetPlatform === "linux" && !allowed(row.libc, "glibc"))) continue;
  const metadata = path.join(root, relative, "package.json");
  if (!fs.existsSync(metadata) && row.optional) continue;
  if (!fs.existsSync(metadata)) throw Error(`Missing runtime package: ${relative}`);
  const installed = JSON.parse(fs.readFileSync(metadata, "utf8"));
  if (installed.version !== row.version) throw Error(`Runtime/lock mismatch: ${relative} ${installed.version} != ${row.version}`);
  checked++;
}
if (process.argv.includes("--archive")) {
  const marker = fs.readFileSync(path.join(root, "node_modules/.stl-runtime-lock.sha256"), "utf8").trim();
  if (marker !== crypto.createHash("sha256").update(lockBytes).digest("hex")) throw Error("Offline runtime was prepared for another lockfile. Recreate the archive.");
}
console.log(`Verified ${checked} runtime package versions against lockfile; Node ${process.versions.node}.`);
