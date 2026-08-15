import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  inferBrowserApiBase,
  normalizePublicResourceUrl,
  resolveBrowserApiBase,
} from "../lib/runtime-api.ts";
import { GET as redirectTheorySchoolDetail } from "../app/admin/theory-schools/[entityId]/route.ts";
import { GET as redirectTheorySchools } from "../app/admin/theory-schools/route.ts";

const lanLocation = {
  protocol: "http:",
  hostname: "192.168.5.6",
  port: "18080",
  origin: "http://192.168.5.6:18080",
};

test("DX4600 LAN ports keep authentication and API traffic on the edge origin", () => {
  assert.equal(inferBrowserApiBase(lanLocation), "/api");
});

test("local preview and public HTTPS default to the same-origin API route", () => {
  assert.equal(
    inferBrowserApiBase({
      protocol: "http:",
      hostname: "localhost",
      port: "3100",
      origin: "http://localhost:3100",
    }),
    "/api",
  );
  assert.equal(
    inferBrowserApiBase({
      protocol: "https:",
      hostname: "library.example.org",
      port: "",
      origin: "https://library.example.org",
    }),
    "/api",
  );
});

test("runtime configuration overrides inference only when valid", () => {
  assert.equal(resolveBrowserApiBase(lanLocation, { apiBase: "/api" }), "/api");
  assert.equal(
    resolveBrowserApiBase(lanLocation, { apiBase: "http://10.0.0.2:9000/api/" }),
    "http://10.0.0.2:9000/api",
  );
  assert.equal(
    resolveBrowserApiBase(lanLocation, { apiBase: "javascript:alert(1)" }),
    "/api",
  );
});

test("reader file URLs accidentally pointing at localhost are repaired", () => {
  const previousWindow = globalThis.window;
  globalThis.window = {
    location: lanLocation,
    __SOCIAL_THEORY_LIBRARY_CONFIG__: { apiBase: "" },
  };
  try {
    assert.equal(
      normalizePublicResourceUrl(
        "http://localhost:8000/api/distribution/assets/asset-id/file/?token=short",
      ),
      "/api/distribution/assets/asset-id/file/?token=short",
    );
    assert.equal(
      normalizePublicResourceUrl("/api/distribution/assets/asset-id/file/"),
      "/api/distribution/assets/asset-id/file/",
    );
    assert.equal(
      normalizePublicResourceUrl("https://objects.example.org/signed/file.pdf"),
      "https://objects.example.org/signed/file.pdf",
    );
  } finally {
    if (previousWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = previousWindow;
    }
  }
});

test("legacy theory admin routes redirect with relative locations and preserve the request target", async () => {
  const listResponse = redirectTheorySchools(new Request(
    "http://127.0.0.1:13100/admin/theory-schools?page=3&search=%E7%8E%B0%E4%BB%A3%E6%80%A7",
  ));
  assert.equal(listResponse.status, 307);
  assert.equal(
    listResponse.headers.get("location"),
    "/admin/theory-nodes?node_type=theory_tradition&page=3&search=%E7%8E%B0%E4%BB%A3%E6%80%A7",
  );

  const detailResponse = await redirectTheorySchoolDetail(
    new Request("http://127.0.0.1:13100/admin/theory-schools/legacy-id?tab=relations"),
    { params: Promise.resolve({ entityId: "legacy id/with spaces" }) },
  );
  assert.equal(detailResponse.status, 307);
  assert.equal(
    detailResponse.headers.get("location"),
    "/admin/theory-nodes?node_type=theory_tradition&legacy_id=legacy+id%2Fwith+spaces&tab=relations",
  );
});

test("cookie-session refresh drops stale bearer headers in JSON and streaming clients", () => {
  const source = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  const removals = source.match(/headers\.delete\("Authorization"\)/g) ?? [];
  assert.equal(removals.length, 2);
});
