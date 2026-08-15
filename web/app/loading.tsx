export default function Loading() {
  return (
    <section className="route-loading" aria-live="polite" aria-busy="true">
      <span className="route-loading-line wide" />
      <span className="route-loading-line" />
      <div className="route-loading-grid">
        <span />
        <span />
        <span />
      </div>
      <p>正在载入内容……</p>
    </section>
  );
}
