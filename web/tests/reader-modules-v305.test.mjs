import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  clampReaderPage,
  readerThumbnailPages,
  useReaderNavigation,
} from "../components/reader/use-reader-navigation.ts";
import { cleanTextLocally } from "../components/reader/use-reader-selection.ts";
import { buildReaderPageOverlays } from "../components/reader/use-reader-page-overlays.ts";

test("reader navigation preserves page bounds and rounded jumps", () => {
  assert.equal(clampReaderPage(-3, 200), 1);
  assert.equal(clampReaderPage(Number.NaN, 200), 1);
  assert.equal(clampReaderPage(12.7, 200), 13);
  assert.equal(clampReaderPage(240, 200), 200);
});

test("reader thumbnail navigation retains full and bounded page windows", () => {
  assert.deepEqual(readerThumbnailPages(1, 3), [1, 2, 3]);
  assert.equal(readerThumbnailPages(400, 400).length, 400);
  for (const [page, first, last] of [[1, 1, 240], [300, 180, 419], [1000, 761, 1000]]) {
    const pages = readerThumbnailPages(page, 1000);
    assert.equal(pages.length, 240);
    assert.equal(pages[0], first);
    assert.equal(pages.at(-1), last);
    assert.ok(pages.every((value, index) => value === first + index));
  }
});

test("reader navigation keeps initial page, zoom and access page count compatible", () => {
  function NavigationProbe() {
    const navigation = useReaderNavigation({ initialPage: 8, initialPageCount: 10, accessPageCount: 12 });
    return createElement("output", {
      "data-page": navigation.page,
      "data-pages": navigation.totalPages,
      "data-zoom": navigation.zoom,
      "data-scroll-page": navigation.scrollRequest.page,
      "data-scroll-behavior": navigation.scrollRequest.behavior,
    });
  }
  const html = renderToStaticMarkup(createElement(NavigationProbe));
  assert.match(html, /data-page="8"/);
  assert.match(html, /data-pages="12"/);
  assert.match(html, /data-zoom="100"/);
  assert.match(html, /data-scroll-page="8"/);
  assert.match(html, /data-scroll-behavior="auto"/);
});

test("reader clean copy preserves existing line, hyphen and punctuation handling", () => {
  assert.equal(cleanTextLocally("  inter-\nnational  theory \n study , example\u00ad .  "), "international theory study, example.");
  assert.equal(cleanTextLocally("社会理论\n与实践 ， 研究 。"), "社会理论 与实践， 研究。");
  assert.equal(cleanTextLocally("\n\t  "), "");
});

test("reader shell delegates selection, navigation and private mutations to real modules", async () => {
  const shell = await readFile(new URL("../components/reader-shell.tsx", import.meta.url), "utf8");
  assert.match(shell, /useReaderNavigation\(/);
  assert.match(shell, /useReaderSelection\(/);
  assert.match(shell, /useReaderRecords\(/);
  assert.match(shell, /useReaderDocument\(/);
  assert.match(shell, /useReaderPageRequest\(/);
  assert.match(shell, /useReaderSearch\(/);
  assert.match(shell, /useReaderCitation\(/);
  assert.match(shell, /useReaderProgress\(/);
  assert.match(shell, /useReaderPageOverlays\(/);
  assert.doesNotMatch(shell, /function captureSelection|function persistAnnotation|function toggleBookmark|setScrollRequest\(/);
  assert.doesNotMatch(shell, /apiRequest|function copyCitation|function jumpToSearchMatch/);
  // Local layout and Escape effects belong to the UI; private writes remain
  // in the record hooks, not forbidden merely because the shell has an effect.
  assert.match(shell, /readerDocumentRef/);
  assert.match(shell, /<PdfContinuousViewer[\s\S]*url=\{access\.url\}/);
  assert.match(shell, /onCopy=\{handleDocumentCopy\}/);
});

test("reader overlays retain canonical dimensions, ordered highlights and private note anchors", () => {
  const canonicalBlocks = [{ id: "block-7", text: "正式原文", bbox: [0, 0, 20, 20] }];
  const annotation = {
    id: "note-7", kind: "note", selector: { page_index: 7, bboxes: [[10, 20, 30, 40]] },
    body_text: "私人笔记", quote: "原句", created_at: "2026-01-01T00:00:00Z",
  };
  const options = {
    annotations: [annotation], focusedAnnotationId: annotation.id,
    pagePayloads: { 7: { width: 600, height: 800, blocks: canonicalBlocks } },
    passageFocus: { page_index: 7, width: 900, height: 900, bbox: [1, 2, 3, 4] },
    query: "原文",
    searchMatches: [{ page_index: 7, width: 1000, height: 1000, highlights: [{ bbox: [5, 6, 7, 8] }] }],
  };
  const overlay = buildReaderPageOverlays(options)[7];
  assert.equal(overlay.sourceWidth, 600);
  assert.equal(overlay.sourceHeight, 800);
  assert.equal(overlay.canonicalBlocks, canonicalBlocks);
  assert.deepEqual(overlay.highlights.map(({ bbox, kind }) => [bbox, kind]), [
    [[1, 2, 3, 4], "search"], [[5, 6, 7, 8], "search"], [[10, 20, 30, 40], "note"],
  ]);
  assert.equal(overlay.notes[0].id, annotation.id);
  assert.equal(overlay.notes[0].body, annotation.body_text);
  assert.equal(overlay.notes[0].quote, annotation.quote);
  assert.equal(overlay.notes[0].focused, true);
  assert.deepEqual(overlay.notes[0].bbox, annotation.selector.bboxes[0]);
  assert.equal(buildReaderPageOverlays({ ...options, query: "" })[7].highlights.length, 2);
});
