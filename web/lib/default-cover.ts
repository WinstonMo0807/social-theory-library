/** A deterministic shuffle keeps a work recognizable across routes and SSR. */
export function defaultCoverVariant(identity: string): number {
  let hash = 2166136261;
  for (const char of identity.normalize('NFC')) {
    hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619);
  }
  return (hash >>> 0) % 6;
}

export function defaultCoverTitle(title: string): string {
  const value = title.replace(/\s+/g, ' ').trim();
  // Keep a complete word where possible; CSS applies the final size-based clamp.
  if (value.length <= 120) return value || '未题名资料';
  const cut = value.slice(0, 117);
  const boundary = cut.lastIndexOf(' ');
  return `${boundary > 85 ? cut.slice(0, boundary) : cut}…`;
}
