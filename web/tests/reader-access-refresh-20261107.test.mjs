import assert from "node:assert/strict";
import test from "node:test";
import { ApiRequestError } from "../lib/api.ts";
import { canRetainReaderAccess } from "../components/reader/use-reader-document.ts";

const current = { requested_asset_id: "book-a", served_asset_id: "normalized-a", url: "/authorized-file" };
test("temporary refresh failures preserve an already authorized document", () => {
  // The response body can time out after fetch has returned successful headers.
  for (const name of ["TimeoutError", "NetworkError"]) {
    assert.equal(canRetainReaderAccess(current, "book-a", Infinity, new DOMException("signal timed out", name), 100), true);
  }
  for (const status of [0, 408, 429, 500, 502, 503, 504]) {
    assert.equal(canRetainReaderAccess(current, "book-a", Infinity, new ApiRequestError("temporary", status), 100), true);
    assert.equal(canRetainReaderAccess(current, "book-a", 200, new ApiRequestError("temporary", status), 100), true);
  }
});
test("revoked, withdrawn, changed and invalid sources clear the document", () => {
  for (const status of [400, 401, 403, 404, 409, 410, 422]) {
    assert.equal(canRetainReaderAccess(current, "book-a", Infinity, new ApiRequestError("unavailable", status), 100), false);
  }
  assert.equal(canRetainReaderAccess(current, "book-a", Infinity, new Error("unexpected payload"), 100), false);
});
test("a previous book or expired signed URL cannot become a fallback", () => {
  const timeout = new ApiRequestError("timeout", 0);
  assert.equal(canRetainReaderAccess(null, "book-a", Infinity, timeout, 100), false);
  assert.equal(canRetainReaderAccess(current, "book-b", Infinity, timeout, 100), false);
  assert.equal(canRetainReaderAccess(current, "book-a", 100, timeout, 100), false);
  assert.equal(canRetainReaderAccess(current, "book-a", 99, timeout, 100), false);
});
