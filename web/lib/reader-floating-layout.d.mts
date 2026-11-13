export type FloatingLayout = { refresh(): void; reset(): void; destroy(): void };
export function clampOffset(offset: {x:number;y:number}, base: {left:number;top:number;width:number;height:number}, viewport:{width:number;height:number}, margin?:number):{x:number;y:number};
export function createReaderFloatingLayout(root: HTMLElement, storageKey: string, options?: {bounds?: HTMLElement}): FloatingLayout;
