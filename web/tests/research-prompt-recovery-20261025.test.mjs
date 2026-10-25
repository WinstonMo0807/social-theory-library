// Deferred acceptance; not executed in the development stage.
import test from "node:test";
import assert from "node:assert/strict";
import { parseResearchPrompt, researchPromptKey } from "../lib/research-prompt-recovery.ts";

const body = { version: 1, owner: "7", project: "research-a", at: 1792886400000, input: { question: "哪些材料需要核对", scope: "selected" } };
test("recovery stays with its original account and research", () => {
  assert.deepEqual(parseResearchPrompt(JSON.stringify(body), "7", "research-a"), body);
  assert.throws(() => parseResearchPrompt(JSON.stringify(body), "8", "research-a"));
  assert.throws(() => parseResearchPrompt(JSON.stringify(body), "7", "research-b"));
  assert.notEqual(researchPromptKey("7", "research-a"), researchPromptKey("8", "research-a"));
});
test("restoration retains input only and rejects corrupt or oversized content", () => {
  assert.deepEqual(parseResearchPrompt(JSON.stringify({ ...body, token: "synthetic-forbidden-extra", input: { ...body.input, quote: "must not be cached" } }), "7", "research-a"), body);
  for (const raw of ["not-json", " ".repeat(20001), JSON.stringify({ ...body, input: { question: "x".repeat(1201), scope: "library" } }), JSON.stringify({ ...body, input: { question: "范围", scope: "unknown" } })]) assert.throws(() => parseResearchPrompt(raw, "7", "research-a"));
  assert.equal(parseResearchPrompt(null, "7", "research-a"), null);
});
