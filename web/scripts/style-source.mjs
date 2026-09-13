import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import postcss from "postcss";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const globalStylesPath = resolve(webRoot, "app/globals.css");

/** Expand only local, unconditional CSS imports in their original cascade order. */
export function readStyleSource(file = globalStylesPath, { exclude = [], seen = [] } = {}) {
  const absolute = file instanceof URL ? fileURLToPath(file) : resolve(file);
  if (seen.includes(absolute)) throw new Error(`Circular CSS import: ${absolute}`);
  const root = postcss.parse(readFileSync(absolute, "utf8"), { from: absolute });
  root.walkAtRules("import", (rule) => {
    const local = rule.params.match(/^["'](\.[^"']+)["']$/)?.[1];
    if (!local) return;
    const target = resolve(dirname(absolute), local);
    if (exclude.includes(target)) {
      rule.remove();
      return;
    }
    const content = readStyleSource(target, { exclude, seen: [...seen, absolute] });
    rule.replaceWith(postcss.parse(content, { from: target }).nodes);
  });
  return root.toString();
}

/** Ignore formatting/comments, but preserve selectors, declarations and at-rule order. */
export function styleSemanticSnapshot(css, { resolveTokens = false } = {}) {
  const root = postcss.parse(css);
  const tokens = new Map();
  if (resolveTokens) {
    root.walkDecls(/^--stl-/, (decl) => {
      if (decl.parent.type !== "rule" || decl.parent.selector !== ":root") {
        throw new Error(`Design token unexpectedly scoped: ${decl.prop}`);
      }
      if (tokens.has(decl.prop)) throw new Error(`Duplicate design token: ${decl.prop}`);
      if (decl.value.includes("var(")) throw new Error(`Migration tokens must retain literal values: ${decl.prop}`);
      tokens.set(decl.prop, decl.value);
    });
  }
  function value(input) {
    if (!resolveTokens) return input;
    return input.replace(/var\((--stl-[\w-]+)\)/g, (_, name) => {
      if (!tokens.has(name)) throw new Error(`Undefined design token: ${name}`);
      return tokens.get(name);
    });
  }
  let rules = 0;
  let declarations = 0;
  function normalize(node) {
    if (node.type === "comment") return null;
    if (node.type === "decl") {
      if (resolveTokens && tokens.has(node.prop)) return null;
      declarations += 1;
      return ["decl", node.prop, value(node.value), Boolean(node.important)];
    }
    const children = node.nodes?.map(normalize).filter(Boolean);
    if (node.type === "rule") {
      if (!children.length) return null;
      rules += 1;
      return ["rule", node.selector, children];
    }
    if (node.type === "atrule") return ["atrule", node.name, node.params, children ?? null];
    if (node.type === "root") return children;
    throw new Error(`Unsupported CSS node: ${node.type}`);
  }
  const nodes = normalize(root);
  return {
    sha256: createHash("sha256").update(JSON.stringify(nodes)).digest("hex"),
    rules,
    declarations,
  };
}
