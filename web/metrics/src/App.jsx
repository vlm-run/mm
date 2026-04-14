import { useState, useEffect, Suspense } from "react";
import pages from "./pages/registry";

// ── Hash-based router ────────────────────────────────────────────

function useHashRoute(defaultId) {
  const [route, setRoute] = useState(() => {
    const hash = window.location.hash.replace("#", "");
    return pages.find((p) => p.id === hash) ? hash : defaultId;
  });

  useEffect(() => {
    const onHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (pages.find((p) => p.id === hash)) setRoute(hash);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = (id) => {
    window.location.hash = id;
    setRoute(id);
  };

  return [route, navigate];
}

// ── Shell ────────────────────────────────────────────────────────

export default function App() {
  const [route, navigate] = useHashRoute(pages[0].id);
  const current = pages.find((p) => p.id === route);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-[var(--panel)] border-b border-[var(--border)] shadow-[var(--shadow-panel)] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-[16px] font-semibold text-[var(--text-primary)]">
              mm <span style={{ color: "var(--accent)" }}>metrics</span>
            </h1>
            <span className="font-mono text-[10px] text-[var(--text-muted)] border border-[var(--border)] rounded px-1.5 py-0.5">v{__MM_VERSION__}</span>
          </div>

          <nav className="flex gap-1">
            {pages.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate(p.id)}
                className={`nav-link px-3 py-1.5 rounded-md text-[12px] font-medium flex items-center gap-1.5 ${
                  route === p.id ? "active" : "text-[var(--text-secondary)]"
                }`}
              >
                {p.label}
                <span
                  className="font-mono text-[9px] font-semibold px-1 py-0 rounded"
                  style={{
                    background: route === p.id ? "rgba(255,255,255,0.2)" : "var(--bg)",
                    color: route === p.id ? "#fff" : "var(--text-muted)",
                  }}
                >
                  {p.tag}
                </span>
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-20">
              <div className="font-mono text-[12px] text-[var(--text-muted)]">Loading...</div>
            </div>
          }
        >
          {current && <current.component />}
        </Suspense>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border)] bg-[var(--panel)]">
        <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center justify-between">
          <span className="font-mono text-[10px] text-[var(--text-muted)]">mm — multimodal context management</span>
          <span className="font-mono text-[10px] text-[var(--text-muted)]">token estimates are approximate</span>
        </div>
      </footer>
    </div>
  );
}
