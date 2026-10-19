import { expect, test } from "@playwright/test";
import { citationText, type SharedCitationPreview } from "../lib/api/shared-citation.client";
import { researchEvidenceReference } from "../lib/api/research-evidence";
import { evidenceIdentity } from "../lib/api/research-navigation";
import { readLocalCitationMaterials, writeLocalCitationMaterials } from "../lib/local-citation-materials";

// Synthetic contract cases only; not executed during implementation.
const ref = { asset_id: "90000000-0000-4000-8000-000000000001", document_revision_id: "90000000-0000-4000-8000-000000000002",
  pdf_page: 2, content_hash: "a".repeat(64), selection_start: 1, selection_end: 5, source_status: "available", quote: "合成原文" };
const citations = { apa: "合成 APA", mla: "合成 MLA", chicago: "合成 Chicago", harvard: "合成 Harvard", "gbt7714-2025": "合成 GB/T", csl: { title: "合成文献" } };
test("range identity keeps different excerpts from the same page separate", async () => {
  expect(await evidenceIdentity(ref)).not.toBe(await evidenceIdentity({ ...ref, selection_start: 7, selection_end: 11 }));
  expect(researchEvidenceReference(ref)).toMatchObject({ selection_start: 1, selection_end: 5 });
});
test("local material storage retains identities and notes without authority text", () => {
  let raw: string | null = null;
  const storage = { getItem: () => raw, setItem: (_: string, value: string) => { raw = value; } };
  writeLocalCitationMaterials([{ id: "test", reference: researchEvidenceReference(ref), note: "本人备注", createdAt: "2026-10-19" }], storage);
  expect(raw).not.toContain("合成原文");
  expect(readLocalCitationMaterials(storage)[0].note).toBe("本人备注");
});
test("legacy or tampered storage preserves original and rejects invalid identity", () => {
  const raw = JSON.stringify([{ id: "bad", reference: { asset_id: "not-an-id" }, note: "", createdAt: "2026-10-19" }]);
  let writes = 0;
  expect(() => readLocalCitationMaterials({ getItem: () => raw, setItem: () => { writes += 1; } })).toThrow();
  expect(writes).toBe(0);
});
test("rendered quote and bibliographic formats remain different outputs", () => {
  const preview: SharedCitationPreview = { reference: ref, citations, source: { edition_id: "90000000-0000-4000-8000-000000000003",
    work_id: "90000000-0000-4000-8000-000000000004", title: "合成文献", authors: [], publication_year: null, publisher: "",
    cover_url: null, work_url: "/works/90000000-0000-4000-8000-000000000003", reader_url: null, pdf_page: 2, printed_label: "", source_status: "available" } };
  expect(citationText(preview, "quote")).toBe("合成原文\n\n合成 GB/T");
  expect(citationText(preview, "apa")).toBe("合成 APA");
  expect(JSON.parse(citationText(preview, "csl"))).toEqual({ title: "合成文献" });
});
