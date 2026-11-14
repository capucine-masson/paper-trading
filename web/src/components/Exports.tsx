import { EXPORT_LINKS, exportUrl } from "../api";

export function Exports() {
  return (
    <section className="card">
      <h2>Export</h2>
      <p className="muted">Download the data behind this dashboard.</p>
      <div className="links">
        {EXPORT_LINKS.map((link) => (
          <a key={link.file} className="button" href={exportUrl(link.file)} download>
            {link.label}
          </a>
        ))}
      </div>
    </section>
  );
}
