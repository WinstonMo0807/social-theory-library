// Page-local opt-in: ordinary links keep working without animation support or JS.
// Keeping this style in the document (rather than a global stylesheet) limits the
// cross-document transition to the welcome page and library home.
export function LibraryEntryTransition() {
  return <style>{`
    @view-transition { navigation: auto; }
    .site-header { view-transition-name: stl-entry-header; }
    ::view-transition-old(root) {
      animation: stl-entry-leave 180ms ease-out both;
    }
    ::view-transition-new(root) {
      animation: stl-entry-arrive 280ms cubic-bezier(.22,1,.36,1) both;
    }
    ::view-transition-group(stl-entry-header) { animation-duration: 0s; }
    ::view-transition-old(stl-entry-header) { display: none; }
    ::view-transition-new(stl-entry-header) { animation: none; }
    @keyframes stl-entry-leave { to { opacity: 0; } }
    @keyframes stl-entry-arrive {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      @view-transition { navigation: none; }
      ::view-transition-group(*) { animation: none; }
    }
  `}</style>;
}
