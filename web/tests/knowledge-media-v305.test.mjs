import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { knowledgeImageEndpoint } from "../lib/api/knowledge-media.ts";

test("knowledge image requests retain their explicit object scope", () => {
  assert.equal(knowledgeImageEndpoint("knowledge_node", "node/id"), "/catalog/admin/knowledge-media/knowledge_node/node%2Fid/");
  assert.equal(knowledgeImageEndpoint("reading_path", "path"), "/catalog/admin/knowledge-media/reading_path/path/");
});

test("public banners and portraits share the same runtime-aware image renderer", async () => {
  const banner = await readFile(new URL("../components/theory-system-ui.tsx", import.meta.url), "utf8");
  const portrait = await readFile(new URL("../components/responsive-portrait-image.tsx", import.meta.url), "utf8");
  assert.match(banner, /ResponsiveMediaImage/);
  assert.match(portrait, /ResponsiveMediaImage/);
  assert.match(banner, /alt=\{media.alt_text/);
});

test("knowledge image clearing checks the displayed fingerprint and explicit confirmation", async () => {
  const source = await readFile(new URL("../components/admin/media/knowledge-image-panel.tsx", import.meta.url), "utf8");
  assert.match(source, /confirmation !== resource.data.fingerprint/);
  assert.match(source, /sending.current/);
  assert.match(source, /ConfirmDialog/);
  assert.match(source, /can_edit_draft_authority/);
});
