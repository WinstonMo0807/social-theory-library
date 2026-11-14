/** The container entrypoint supplies the same validated value as runtime-config.js. */
export function runtimeApiBootstrap(apiBase: string | undefined) {
  if (apiBase === undefined) return null;
  const config = JSON.stringify({ apiBase }).replaceAll("<", "\\u003c").replaceAll("\u2028", "\\u2028").replaceAll("\u2029", "\\u2029");
  return `window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze(${config});`;
}
