/** Hit-test the displayed boxes so selection, zoom and rotation keep their native behavior. */
export function readerAnnotationTargets(root: ParentNode, x: number, y: number): string[] {
  const ids = new Set<string>();
  root.querySelectorAll<HTMLElement>("[data-reader-annotation-id]").forEach(element => {
    const box = element.getBoundingClientRect();
    if (box.width > 0 && box.height > 0 && x >= box.left - 2 && x <= box.right + 2 && y >= box.top - 2 && y <= box.bottom + 2) {
      if (element.dataset.readerAnnotationId) ids.add(element.dataset.readerAnnotationId);
    }
  });
  return [...ids];
}
