import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const code = readFileSync(new URL("../public/typography-init.js", import.meta.url), "utf8");
function apply(hash, entries = {}, blocked = false) {
  const values = new Map(Object.entries(entries));
  const dataset = {};
  vm.runInNewContext(code, {
    URLSearchParams,
    window: { location: { hash }, addEventListener() {} },
    document: { documentElement: { dataset } },
    sessionStorage: {
      getItem(key) { if (blocked) throw Error("blocked"); return values.get(key); },
      setItem(key, value) { if (blocked) throw Error("blocked"); values.set(key, value); },
    },
  });
  return dataset;
}
assert.deepEqual(apply("", { "stl-typography": "B" }), { typeset: "A", typeface: "balanced" });
assert.deepEqual(apply("#typography=A&font=wenkai"), { typeset: "A", typeface: "wenkai" });
assert.deepEqual(apply("#typography=B"), { typeset: "B", typeface: "balanced" });
assert.deepEqual(apply("#section", { "stl-font-trial": "song" }), { typeset: "A", typeface: "song" });
assert.deepEqual(apply("#font=unknown", { "stl-font-trial": "invalid" }), { typeset: "A", typeface: "balanced" });
assert.deepEqual(apply("#typography=A&font=sans", {}, true), { typeset: "A", typeface: "sans" });
console.log("A default, explicit trials, storage fallback: passed");
