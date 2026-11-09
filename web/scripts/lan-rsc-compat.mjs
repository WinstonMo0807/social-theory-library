// LAN HTTP has no crypto.subtle. Vinext accepts its own legacy hash on the
// server; use that existing protocol only in the isolated demo configuration.
export function lanRscCompat() {
  return {
    name: 'stl-lan-rsc-compat',
    enforce: 'pre',
    transform(code, id) {
      if (!id.replaceAll('\\', '/').split('?')[0].endsWith('/vinext/dist/server/app-rsc-cache-busting.js')) return;
      const signature = 'async function sha256CacheBustingHash(input) {';
      if (!code.includes(signature)) throw new Error('Vinext RSC cache protocol changed; review the LAN adapter.');
      return { code: code.replace(signature, `${signature}\n\tif (!globalThis.crypto?.subtle) return fnv1a64(input);`), map: null };
    },
  };
}
