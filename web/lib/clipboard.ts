/** Reject as a promise even when an HTTP browser has no Clipboard API. */
export async function writeClipboardText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}
