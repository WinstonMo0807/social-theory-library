import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const files = readdirSync(resolve(webRoot, "tests"))
  .filter((file) => file.endsWith(".test.mjs")).sort()
  .map((file) => resolve(webRoot, "tests", file));
if (!files.length) throw new Error("No unit tests discovered.");
const result = spawnSync(process.execPath, ["--import", "tsx", "--test", "--test-force-exit", ...files], { cwd: webRoot, stdio: "inherit" });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
