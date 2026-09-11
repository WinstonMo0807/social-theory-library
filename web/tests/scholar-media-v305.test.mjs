import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { adaptApiScholar } from "../lib/public-data-adapters.ts";

test("scholar adapter keeps exact published portrait renditions and alt text", () => {
  const media = { alt_text: "本人肖像及来源说明", renditions: [{ id: "r1", width: 320, height: 400, url: "/api/portrait/?rendition=r1" }] };
  const value = { slug: "scholar", person: { id: "p1", preferred_name: "学者", original_name: "Scholar", portrait: "/api/portrait/?rendition=r1", portrait_media: media } };
  const adapted = adaptApiScholar(value);
  assert.equal(adapted.portrait, value.person.portrait);
  assert.equal(adapted.portraitSources, media.renditions);
  assert.equal(adapted.portraitAlt, media.alt_text);
});

test("legacy portrait remains readable without inventing responsive variants", () => {
  const scholar = adaptApiScholar({ slug: "old", person: { id: "p1", preferred_name: "旧学者", portrait: "/media/public/people/old.jpg" } });
  assert.equal(scholar.portrait, "/media/public/people/old.jpg");
  assert.equal(scholar.portraitSources, undefined);
});

test("scholar editor shares media storage and keeps destructive selection explicitly confirmed", async () => {
  const panel = await readFile(new URL("../components/admin/media/scholar-portrait-panel.tsx", import.meta.url), "utf8");
  const editor = await readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8");
  assert.match(panel, /ConfirmDialog/);
  assert.match(panel, /expected_person_id: resource.data.person_id/);
  assert.match(panel, /confirmed !== confirmationKey/);
  assert.match(panel, /sending.current/);
  assert.doesNotMatch(editor, /portraitBody.append/);
  assert.match(editor, /ScholarPortraitPanel/);
});
