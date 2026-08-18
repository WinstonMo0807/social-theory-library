import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ApiRequestError,
  apiRequest,
  clearStoredSession,
  getServerSessionCredential,
  logoutCurrentSession,
  subscribeToSessionChanges,
} from "../lib/api.ts";
import { bootstrapSession } from "../lib/session.ts";

function response(status, payload = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installBrowser(t, { hint = false, storageThrows = false, locks } = {}) {
  const originals = new Map();
  for (const key of ["window", "document", "navigator", "fetch"]) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  }
  const values = new Map(hint ? [["library_session_active", "1"]] : []);
  const storageListeners = new Set();
  const localStorage = {
    getItem(key) {
      if (storageThrows) throw new Error("storage disabled");
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      if (storageThrows) throw new Error("storage disabled");
      values.set(key, String(value));
    },
    removeItem(key) {
      if (storageThrows) throw new Error("storage disabled");
      values.delete(key);
    },
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      location: {
        protocol: "https:",
        hostname: "books.example.test",
        port: "",
        origin: "https://books.example.test",
      },
      localStorage,
      addEventListener(type, listener) {
        if (type === "storage") storageListeners.add(listener);
      },
      removeEventListener(type, listener) {
        if (type === "storage") storageListeners.delete(listener);
      },
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    writable: true,
    value: { cookie: "csrftoken=test-csrf" },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    writable: true,
    value: { locks },
  });
  clearStoredSession();
  if (hint && !storageThrows) values.set("library_session_active", "1");

  t.after(() => {
    clearStoredSession();
    for (const [key, descriptor] of originals) {
      if (descriptor) {
        Object.defineProperty(globalThis, key, descriptor);
      } else {
        delete globalThis[key];
      }
    }
  });
  return {
    values,
    setFetch(handler) {
      Object.defineProperty(globalThis, "fetch", {
        configurable: true,
        writable: true,
        value: handler,
      });
    },
    emitStorage(key, newValue) {
      for (const listener of storageListeners) listener({ key, newValue });
    },
  };
}

const reader = {
  id: 7,
  email: "reader@example.test",
  display_name: "Reader",
  role: "reader",
};

test("valid HttpOnly cookie recovers a session without a localStorage hint", async (t) => {
  const browser = installBrowser(t);
  let meCalls = 0;
  browser.setFetch(async (url, options) => {
    assert.equal(options.credentials, "include");
    assert.match(String(url), /\/auth\/me\/$/);
    meCalls += 1;
    return response(200, reader);
  });

  const session = await bootstrapSession();

  assert.equal(session.status, "authenticated");
  assert.equal(session.user?.email, reader.email);
  assert.equal(meCalls, 1);
  assert.equal(browser.values.get("library_session_active"), "1");
});

test("browser storage failure cannot block a valid cookie session", async (t) => {
  const browser = installBrowser(t, { storageThrows: true });
  browser.setFetch(async () => response(200, reader));

  const session = await bootstrapSession();

  assert.equal(session.status, "authenticated");
  assert.equal(getServerSessionCredential(), "cookie-session");
});

test("stale hint is cleared only after an unrecoverable 401", async (t) => {
  const browser = installBrowser(t, { hint: true });
  browser.setFetch(async (url) => (
    String(url).includes("/auth/token/refresh/") ? response(401) : response(401)
  ));

  const session = await bootstrapSession();

  assert.equal(session.status, "unauthenticated");
  assert.equal(session.errorCategory, "auth_401");
  assert.equal(browser.values.has("library_session_active"), false);
});

for (const [name, fetchResult, expectedStatus, expectedCategory] of [
  ["auth 403", async () => response(403, { detail: "forbidden" }), "forbidden", "auth_403"],
  ["auth 500", async () => response(500), "temporary_error", "auth_5xx"],
  ["network error", async () => { throw new TypeError("offline"); }, "temporary_error", "network_error"],
]) {
  test(`${name} retains the local session hint`, async (t) => {
    const browser = installBrowser(t, { hint: true });
    browser.setFetch(fetchResult);

    const session = await bootstrapSession();

    assert.equal(session.status, expectedStatus);
    assert.equal(session.errorCategory, expectedCategory);
    assert.equal(browser.values.get("library_session_active"), "1");
  });
}

test("reader and admin roles are distinguished after the same bootstrap", async (t) => {
  const browser = installBrowser(t);
  browser.setFetch(async () => response(200, reader));
  const forbidden = await bootstrapSession({ allowedRoles: ["admin", "editor", "reviewer"] });
  assert.equal(forbidden.status, "forbidden");
  assert.equal(forbidden.user?.role, "reader");

  browser.setFetch(async () => response(200, { ...reader, role: "admin" }));
  const allowed = await bootstrapSession({ allowedRoles: ["admin", "editor", "reviewer"] });
  assert.equal(allowed.status, "authenticated");
});

test("refresh 403 and service failures do not clear the session", async (t) => {
  const browser = installBrowser(t, { hint: true });
  browser.setFetch(async (url) => (
    String(url).includes("/auth/token/refresh/") ? response(403) : response(401)
  ));

  await assert.rejects(
    apiRequest("/protected/", {}, "cookie-session"),
    (error) => error instanceof ApiRequestError && error.status === 403,
  );
  assert.equal(browser.values.get("library_session_active"), "1");
});

test("concurrent 401 responses use one refresh request", async (t) => {
  const browser = installBrowser(t, { hint: true });
  let refreshCalls = 0;
  let protectedCalls = 0;
  browser.setFetch(async (url) => {
    if (String(url).includes("/auth/token/refresh/")) {
      refreshCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 15));
      return response(200);
    }
    protectedCalls += 1;
    return protectedCalls <= 2 ? response(401) : response(200, { ok: true });
  });

  const results = await Promise.all([
    apiRequest("/protected/", {}, "cookie-session"),
    apiRequest("/protected/", {}, "cookie-session"),
  ]);

  assert.equal(refreshCalls, 1);
  assert.deepEqual(results, [{ ok: true }, { ok: true }]);
});

test("Web Locks and refresh revision prevent duplicate refresh across tabs", async (t) => {
  let tail = Promise.resolve();
  const locks = {
    request(_name, callback) {
      const result = tail.then(callback);
      tail = result.then(() => undefined, () => undefined);
      return result;
    },
  };
  const browser = installBrowser(t, { hint: true, locks });
  let refreshCalls = 0;
  let protectedCalls = 0;
  browser.setFetch(async (url) => {
    if (String(url).includes("/auth/token/refresh/")) {
      refreshCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 15));
      return response(200);
    }
    protectedCalls += 1;
    return protectedCalls <= 2 ? response(401) : response(200, { ok: true });
  });
  const tabA = await import("../lib/api.ts?tab=a");
  const tabB = await import("../lib/api.ts?tab=b");

  const results = await Promise.all([
    tabA.apiRequest("/protected/", {}, "cookie-session"),
    tabB.apiRequest("/protected/", {}, "cookie-session"),
  ]);

  assert.equal(refreshCalls, 1);
  assert.deepEqual(results, [{ ok: true }, { ok: true }]);
});

test("storage changes notify mounted pages to revalidate server state", (t) => {
  const browser = installBrowser(t, { hint: true });
  let notifications = 0;
  const unsubscribe = subscribeToSessionChanges(() => {
    notifications += 1;
  });

  browser.emitStorage("library_session_active", null);
  browser.emitStorage("unrelated", "value");
  unsubscribe();
  browser.emitStorage("library_session_active", "1");

  assert.equal(notifications, 1);
});

test("logout contacts the server even when the local hint is absent", async (t) => {
  const browser = installBrowser(t);
  let logoutCalls = 0;
  browser.setFetch(async (url) => {
    if (String(url).includes("/auth/logout/")) logoutCalls += 1;
    return response(204);
  });

  await logoutCurrentSession();

  assert.equal(logoutCalls, 1);
});

test("Admin and Reader protected surfaces use the shared bootstrap", () => {
  const admin = readFileSync(new URL("../components/admin-shell.tsx", import.meta.url), "utf8");
  const readerCenter = readFileSync(new URL("../components/reader-center.tsx", import.meta.url), "utf8");
  const readerNotes = readFileSync(new URL("../components/reader-book-notes.tsx", import.meta.url), "utf8");

  assert.match(admin, /useSessionBootstrap\(staffRoles\)/);
  assert.doesNotMatch(admin, /if \(!token\).*login/s);
  assert.match(readerCenter, /useSessionBootstrap\(\)/);
  assert.match(readerCenter, /Promise\.allSettled\(requests\)/);
  assert.match(readerCenter, /isUnauthenticatedError\(result\.reason\)/);
  assert.match(readerNotes, /useSessionBootstrap\(\)/);
});
