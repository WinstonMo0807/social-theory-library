/** Read-only documentation checks. No server, database, or external API calls. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const documents = [
  "AGENTS.md", "README.md", "docs/README.md", "docs/CURRENT_STATE.md",
  "docs/GPT_ARCHITECTURE_CONTEXT.md", "docs/ADMIN_ARCHITECTURE_PROFILE.md",
  "docs/INGESTION_AND_PUBLICATION.md", "docs/REDESIGN_BRIEF.md",
  "docs/V3.0.6_ADMIN_CAPABILITY_INVENTORY.md", "docs/V3.0.6_PUBLIC_CONTROL_MATRIX.md",
];
const errors = [];
let links = 0;
let sourcePaths = 0;
for (const document of documents) {
  const text = fs.readFileSync(path.join(root, document), "utf8");
  for (const match of text.matchAll(/\[[^\]\n]*\]\(([^)\n]+)\)/g)) {
    const target = match[1].replace(/^<|>$/g, "").split("#")[0];
    if (!target || /^(?:https?:|mailto:|plugin:|codex:)/.test(target)) continue;
    links++;
    const filename = path.resolve(root, path.dirname(document), decodeURIComponent(target));
    if (!fs.existsSync(filename)) errors.push({ document, missingLink: target });
  }
  for (const match of text.matchAll(/`((?:api|web|scripts|deploy)\/[^`\s*]+\.(?:py|tsx?|mjs|json|css|yaml|yml|template))`/g)) {
    sourcePaths++;
    if (!fs.existsSync(path.join(root, match[1]))) errors.push({ document, missingSource: match[1] });
  }
}
function filesIn(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    return entry.isDirectory() ? filesIn(fullPath) : [fullPath];
  });
}
const appRoot = path.join(root, "web/app");
const routes = filesIn(path.join(appRoot, "admin"))
  .filter((filename) => path.basename(filename) === "page.tsx")
  .map((filename) => "/" + path.relative(appRoot, path.dirname(filename)).replaceAll("\\", "/"))
  .sort();
const inventory = fs.readFileSync(path.join(root, "docs/V3.0.6_ADMIN_CAPABILITY_INVENTORY.md"), "utf8");
const inventoryRoutes = [...inventory.matchAll(/^\| R\d+ \| `([^`]+)` \|/gm)].map((match) => match[1]).sort();
for (const route of routes) {
  if (!inventoryRoutes.includes(route)) errors.push({ missingInventoryRoute: route });
}
for (const route of inventoryRoutes) {
  if (!routes.includes(route)) errors.push({ obsoleteInventoryRoute: route });
}
if (new Set(inventoryRoutes).size !== inventoryRoutes.length) errors.push({ duplicateInventoryRoutes: true });
const registry = fs.readFileSync(path.join(root, "api/catalog/services/public_knowledge_control.py"), "utf8");
const publicContracts = {};
for (const match of registry.matchAll(/_page\("([a-z_]+)",/g)) {
  publicContracts[match[1]] = (publicContracts[match[1]] || 0) + 1;
}
console.log(JSON.stringify({
  scope: "documentation_references_and_source_route_inventory_not_behavioral_acceptance",
  documents: documents.length, localLinks: links, sourcePaths,
  adminPageRoutes: routes.length, inventoryRoutes: inventoryRoutes.length,
  publicContractDeclarations: Object.values(publicContracts).reduce((sum, count) => sum + count, 0),
  publicContracts, errors,
}, null, 2));
process.exitCode = errors.length ? 1 : 0;
