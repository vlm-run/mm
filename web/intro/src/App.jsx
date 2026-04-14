import { useState, useEffect, Suspense } from "react";
import pages from "./pages/registry";

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

export default function App() {
  const [route, navigate] = useHashRoute(pages[0].id);
  const current = pages.find((p) => p.id === route);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-[var(--panel)] border-b border-[var(--border)] sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1
              className="text-[16px] font-semibold tracking-tight"
              style={{ fontFamily: "var(--font-heading)", color: "var(--forest)" }}
            >
              mm <span style={{ color: "var(--coral)" }}>docs</span>
            </h1>
            <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--text-muted)] border border-[var(--border)] rounded-sm px-1.5 py-0.5">
              v{__MM_VERSION__}
            </span>
          </div>

          <nav className="flex gap-1">
            {pages.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate(p.id)}
                className={`nav-link px-3 py-1.5 rounded-sm text-[12px] font-medium ${
                  route === p.id ? "active" : "text-[var(--text-secondary)]"
                }`}
                style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}
              >
                {p.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-20">
              <div className="font-mono text-[12px] text-[var(--text-muted)]">
                Loading...
              </div>
            </div>
          }
        >
          {current && <current.component />}
        </Suspense>
      </main>

      <footer className="border-t border-[var(--border)] bg-[var(--panel)]">
        <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--text-muted)]">
            mm — multimodal context for humans & agents
          </span>
          <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--text-muted)]">
            Rust + Python · Apache 2.0
          </span>
        </div>
      </footer>
    </div>
  );
}
