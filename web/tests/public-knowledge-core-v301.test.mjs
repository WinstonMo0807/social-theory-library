import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Topic and Scholar pages prefer normalized Knowledge Core relations", async () => {
  const [serverApi, topic, scholar, topicSection, scholarSection] = await Promise.all([
    read("../lib/server-api.ts"),
    read("../app/topics/[slug]/page.tsx"),
    read("../app/scholars/[slug]/page.tsx"),
    read("../app/topics/[slug]/[section]/page.tsx"),
    read("../app/scholars/[slug]/[section]/page.tsx"),
  ]);

  assert.match(serverApi, /knowledge_nodes\?: PublicKnowledgeNodeLink\[\]/);
  assert.match(topic, /topic\.knowledgeNodes/);
  assert.match(topic, /href: `\/theories\/nodes\/\$\{node\.slug\}`/);
  assert.match(topicSection, /normalizedTheories\.length/);
  assert.match(scholar, /knowledgeNodes\.filter/);
  assert.match(scholar, /normalizedDebates/);
  assert.match(scholarSection, /normalizedConcepts/);
  assert.doesNotMatch(serverApi, /derived_claims/);
});

test("Reading Path renders canonical learning goals and prerequisites with compatibility fallback", async () => {
  const [serverApi, page] = await Promise.all([
    read("../lib/server-api.ts"),
    read("../app/theories/reading-paths/[slug]/page.tsx"),
  ]);

  assert.match(serverApi, /learning_goal\?: string/);
  assert.match(serverApi, /prerequisite\?: string/);
  assert.match(page, /path\.learning_goal \|\| path\.introduction/);
  assert.match(page, /item\.prerequisite \|\| item\.editorial_note/);
  assert.match(page, /先修条件/);
});
