import assert from "node:assert/strict";
import test from "node:test";
import {
  displayedReaderBox, readerSelectionSourceBox, rotateReaderBox, rotateReaderPoint,
} from "../lib/reader-coordinates.ts";

// Authored for unified acceptance; no PDF or user annotation fixtures.
function close(actual, expected) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-8));
}

test("directory points rotate clockwise in the displayed-page frame", () => {
  close(rotateReaderPoint([.2, .3], 0), [.2, .3]);
  close(rotateReaderPoint([.2, .3], 90), [.7, .2]);
  close(rotateReaderPoint([.2, .3], 180), [.8, .7]);
  close(rotateReaderPoint([.2, .3], 270), [.3, .8]);
});

test("rotated selections return the same saved annotation across page sizes and zoom", () => {
  const original = [.1, .2, .3, .4];
  for (const [sourceWidth, sourceHeight] of [[600, 900], [1600, 1000], [720, 720]]) {
    for (const zoom of [.6, 1, 1.8]) {
      for (const rotation of [0, 90, 180, 270]) {
        const sideways = rotation === 90 || rotation === 270;
        const width = (sideways ? sourceHeight : sourceWidth) * zoom;
        const height = (sideways ? sourceWidth : sourceHeight) * zoom;
        const rotated = rotateReaderBox(original, rotation);
        const rectangle = rotated.map((value, index) => value * (index % 2 ? height : width));
        close(readerSelectionSourceBox(rectangle, width, height, sourceWidth, sourceHeight, rotation),
          original.map((value, index) => value * (index % 2 ? sourceHeight : sourceWidth)));
      }
    }
  }
});

test("server crop and source rotation are not applied a second time", () => {
  for (const sourceRotation of [0, 90, 180, 270]) {
    const normalized_bbox = [.1, .2, .3, .4];
    const canonical = displayedReaderBox({
      geometry_status: "validated", normalized_bbox,
      geometry: { rotation: sourceRotation, coordinate_space: "rendered_pixels" },
    }, 1, 1);
    close(rotateReaderBox(canonical, 90), [.6, .1, .8, .3]);
    close(rotateReaderBox(canonical, 180), [.7, .6, .9, .8]);
    close(rotateReaderBox(canonical, 270), [.2, .7, .4, .9]);
  }
});

test("selection clipping rejects invalid or off-page rectangles before saving", () => {
  close(readerSelectionSourceBox([-10, 20, 120, 80], 100, 100, 600, 900, 90),
    [120, 0, 480, 900]);
  for (const rectangle of [[0, 0, 0, 5], [100, 0, 110, 5], [0, 120, 5, 130], [NaN, 0, 5, 5], [0, 0, 1]]) {
    assert.equal(readerSelectionSourceBox(rectangle, 100, 100, 600, 900, 90), null);
  }
  assert.equal(readerSelectionSourceBox([0, 0, 5, 5], 0, 100, 600, 900, 0), null);
  assert.equal(readerSelectionSourceBox([0, 0, 5, 5], 100, 100, Infinity, 900, 0), null);
});
