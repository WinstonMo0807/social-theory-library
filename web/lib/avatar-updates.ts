"use client";

type AvatarUpdate = { owner: string; revision: number | null };
const eventName = "stl:avatar-updated";

export function announceAvatarUpdate(value: AvatarUpdate) {
  window.dispatchEvent(new CustomEvent(eventName, { detail: value }));
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(eventName);
    channel.postMessage(value);
    channel.close();
  }
}

export function subscribeAvatarUpdates(callback: (value: AvatarUpdate) => void) {
  const accept = (value: AvatarUpdate) => {
    if (value && typeof value.owner === "string" && (value.revision === null || Number.isInteger(value.revision) && value.revision > 0)) callback(value);
  };
  const listener = (event: Event) => accept((event as CustomEvent<AvatarUpdate>).detail);
  window.addEventListener(eventName, listener);
  const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(eventName) : null;
  if (channel) channel.onmessage = event => accept(event.data);
  return () => { window.removeEventListener(eventName, listener); channel?.close(); };
}
