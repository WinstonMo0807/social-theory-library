import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repository = resolve(webRoot, "..");
const python = process.env.STL_CONTRACT_PYTHON || resolve(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const temporary = mkdtempSync(join(tmpdir(), "stl-api-contract-"));
const schemaPath = join(temporary, "schema.json");
const checked = process.argv.includes("--check");
try {
  execFileSync(python, [resolve(repository, "api/manage.py"), "spectacular", "--urlconf", "config.schema_urls", "--format", "openapi-json", "--file", schemaPath, "--validate", "--fail-on-warn"], {
    cwd: repository, stdio: ["ignore", "ignore", "inherit"],
    env: { ...process.env, DATABASE_URL: "sqlite:///:memory:", PYTHONIOENCODING: "utf-8", PUBLIC_DEPLOYMENT_MODE: "false", DJANGO_DEBUG: "true" },
  });
  const schemaText = readFileSync(schemaPath, "utf8");
  const generated = "/** Generated from DRF/OpenAPI. Do not edit by hand. */\n" + astToString(await openapiTS(JSON.parse(schemaText)));
  const files = [[resolve(repository, "api/openapi/schema.json"), schemaText], [resolve(webRoot, "lib/api/generated/schema.ts"), generated]];
  for (const [path, expected] of files) {
    if (checked) {
      if (readFileSync(path, "utf8").replaceAll("\r\n", "\n") !== expected.replaceAll("\r\n", "\n")) throw new Error(`API contract drift: ${path}`);
    } else {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, expected);
    }
  }
  console.log(checked ? "Verified API contracts match serializers." : "Generated verified API contracts from serializers.");
} finally {
  // This exact path is created by mkdtemp above, never from user arguments.
  if (dirname(temporary) !== resolve(tmpdir())) throw new Error("Unsafe temporary directory");
  rmSync(temporary, { recursive: true });
}
