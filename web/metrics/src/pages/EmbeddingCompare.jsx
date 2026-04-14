import { useState, useCallback } from "react";

// ── Model data ───────────────────────────────────────────────────
const MODELS = [
  {
    id: "gemini",
    name: "Gemini Embedding 2",
    model: "gemini-embedding-2-preview",
    provider: "Google",
    pricePerMillion: 0.2,
    batchPrice: null,
    pricePerMillionText: 0.2,
    pricePerMillionImage: 0.45,
    pricePerMillionAudio: 6.5,
    pricePerMillionVideo: 12.0,
    pricePerMillionPdf: 0.2,
    contextTokens: 8192,
    dims: "3 072",
    modality: ["text", "image", "video", "audio", "pdf"],
    hostingNote: "Managed — Gemini API / Vertex AI",
    accent: "#3b82f6",
    tag: "Multimodal",
    modalityPricing: null,
  },
  {
    id: "qwen-vl",
    name: "Qwen3-VL-Embedding",
    model: "qwen3-vl-embedding",
    provider: "Alibaba / Qwen",
    pricePerMillion: 0.1,
    pricePerMillionImage: 0.258,
    pricePerMillionText: 0.1,
    dtype: "float32",
    contextTokens: 32768,
    dims: "2 560, 2 048, 1 536, 1 024, 768, 512, 256",
    modality: ["text", "image", "video", "screenshot"],
    hostingNote: "Managed API — Alibaba Cloud / DashScope",
    accent: "#f59e0b",
    tag: "Multimodal",
    modalityPricing: { text: 0.1, image: 0.258, video: 0.258, screenshot: 0.258 },
  },
  {
    id: "qwen-text",
    name: "Qwen3 Embedding 8B",
    model: "qwen/qwen3-embedding-8b",
    provider: "OpenRouter",
    pricePerMillion: 0.01,
    contextTokens: 32000,
    dims: "4 096",
    modality: ["text"],
    hostingNote: "Managed — OpenRouter API",
    accent: "#10b981",
    tag: "Text-only",
    modalityPricing: null,
  },
];

// ── Use-case data ────────────────────────────────────────────────
const USE_CASES = [
  { id: "rag", name: "Semantic search / RAG", tokensPerDoc: 512, chunkLabel: "512 tok/chunk", description: "512-token chunks, 10% overlap — the standard RAG pipeline sweet spot." },
  { id: "qa", name: "Q&A over docs", tokensPerDoc: 256, chunkLabel: "256 tok/chunk", description: "256-token chunks for high retrieval precision on targeted Q&A tasks." },
  { id: "summ", name: "Summarisation", tokensPerDoc: 1024, chunkLabel: "1 024 tok/chunk", description: "1 024-token chunks to preserve context for coherent summaries." },
  { id: "chat", name: "Chat history", tokensPerDoc: 512, chunkLabel: "512 tok/chunk", description: "Embedding conversation turns for memory/retrieval in agent pipelines." },
  { id: "code", name: "Code retrieval", tokensPerDoc: 1024, chunkLabel: "1 024 tok/chunk", description: "Function/class-level chunks. Qwen3 Embedding leads MTEB-Code benchmarks." },
];

const MODALITY_FILTERS = [
  { id: "all", label: "All" },
  { id: "text", label: "Text" },
  { id: "image", label: "Image" },
  { id: "audio", label: "Audio" },
  { id: "video", label: "Video" },
  { id: "pdf", label: "Documents" },
];

// ── Helpers ──────────────────────────────────────────────────────
function calcCostPerHour(model, docsPerHour, tokensPerDoc, activeModality) {
  const mTokens = (docsPerHour * tokensPerDoc) / 1_000_000;
  let price = model.pricePerMillion;
  if (model.id === "gemini" && activeModality && activeModality !== "all") {
    const p = { text: model.pricePerMillionText, image: model.pricePerMillionImage, audio: model.pricePerMillionAudio, video: model.pricePerMillionVideo, pdf: model.pricePerMillionPdf };
    price = p[activeModality] ?? model.pricePerMillion;
  } else if (model.modalityPricing && activeModality && activeModality !== "all") {
    price = model.modalityPricing[activeModality] ?? model.pricePerMillion;
  } else if (model.id === "qwen-vl" && model.modalityPricing) {
    price = model.pricePerMillionText;
  }
  return mTokens * price;
}

function formatCost(c) {
  if (c === null) return "N/A";
  if (c < 0.0001) return `$${c.toFixed(5)}`;
  if (c < 0.01) return `$${c.toFixed(4)}`;
  if (c < 1) return `$${c.toFixed(3)}`;
  return `$${c.toFixed(2)}`;
}

function modelSupportsModality(model, modality) {
  if (modality === "all") return true;
  return model.modality.includes(modality);
}

// ── Components ───────────────────────────────────────────────────

function ModalityPill({ type }) {
  const map = {
    text: { bg: "#f3f4f6", color: "#374151" },
    image: { bg: "#ede9fe", color: "#5b21b6" },
    video: { bg: "#fce7f3", color: "#9d174d" },
    audio: { bg: "#d1fae5", color: "#065f46" },
    pdf: { bg: "#fee2e2", color: "#991b1b" },
    screenshot: { bg: "#e0f2fe", color: "#0369a1" },
  };
  const s = map[type] || { bg: "#f3f4f6", color: "#374151" };
  return (
    <span className="font-mono text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full inline-block mr-1 mb-1" style={{ background: s.bg, color: s.color }}>
      {type}
    </span>
  );
}

function Bar({ value, maxValue, color }) {
  const pct = maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-[var(--bg)] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.max(pct, 2)}%`, background: color, transition: "width 0.4s ease-in-out" }} />
      </div>
    </div>
  );
}

function ModelCard({ model, cost, maxCost, isLowest, tokensPerHour, activeModality, supported }) {
  if (!supported) {
    const label = MODALITY_FILTERS.find((f) => f.id === activeModality)?.label || activeModality;
    return (
      <div className="panel p-5 opacity-50">
        <div className="font-semibold text-[13px] text-[var(--text-primary)]">{model.name}</div>
        <div className="font-mono text-[11px] text-[var(--text-muted)] mt-0.5">{model.model}</div>
        <div className="mt-4 border border-dashed border-[var(--border-strong)] rounded-lg p-4 text-center">
          <div className="font-mono text-[12px] font-semibold text-[var(--text-secondary)] mb-1">{label} not supported</div>
          <div className="text-[11px] text-[var(--text-muted)]">Supported: {model.modality.join(", ")}</div>
        </div>
      </div>
    );
  }

  let priceLabel = `$${model.pricePerMillion}/1M`;
  if (model.id === "gemini" && activeModality && activeModality !== "all") {
    const p = { text: model.pricePerMillionText, image: model.pricePerMillionImage, audio: model.pricePerMillionAudio, video: model.pricePerMillionVideo, pdf: model.pricePerMillionPdf };
    const v = p[activeModality];
    if (v !== undefined) priceLabel = `$${v}/1M`;
  } else if (model.modalityPricing && activeModality && activeModality !== "all") {
    const v = model.modalityPricing[activeModality];
    if (v !== undefined) priceLabel = `$${v}/1M`;
  } else if (model.id === "gemini") {
    priceLabel = "$0.20–$12.00/1M";
  } else if (model.id === "qwen-vl") {
    priceLabel = "$0.10–$0.258/1M";
  }

  return (
    <div className="panel p-5 relative" style={{ borderColor: isLowest ? model.accent : undefined, boxShadow: isLowest ? `0 0 0 2px ${model.accent}20` : undefined }}>
      {isLowest && (
        <div className="absolute -top-2.5 right-4 text-[10px] font-mono font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full text-white" style={{ background: model.accent }}>
          Lowest
        </div>
      )}

      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="font-semibold text-[13px] text-[var(--text-primary)]">{model.name}</div>
          <div className="font-mono text-[11px] text-[var(--text-muted)] mt-0.5">{model.model}</div>
          {model.dtype && <div className="font-mono text-[10px] text-[var(--text-muted)]">dtype: {model.dtype}</div>}
        </div>
        <span className="font-mono text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${model.accent}15`, color: model.accent }}>
          {model.tag}
        </span>
      </div>

      <div className="mb-3">{model.modality.map((m) => <ModalityPill key={m} type={m} />)}</div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] text-[var(--text-secondary)] mb-4">
        <div><span className="text-[var(--text-muted)]">Provider</span><br /><strong className="text-[var(--text-primary)]">{model.provider}</strong></div>
        <div><span className="text-[var(--text-muted)]">Context</span><br /><strong className="text-[var(--text-primary)] font-mono">{model.contextTokens.toLocaleString()} tok</strong></div>
        <div className="col-span-2"><span className="text-[var(--text-muted)]">Dims</span><br /><strong className="text-[var(--text-primary)] font-mono text-[10px]">{model.dims}</strong></div>
        <div className="col-span-2"><span className="text-[var(--text-muted)]">Price</span><br /><strong className="text-[var(--text-primary)] font-mono">{priceLabel}</strong></div>
      </div>

      <div className="bg-[var(--bg)] rounded-lg p-3">
        <div className="flex justify-between items-baseline">
          <span className="font-mono text-[11px] text-[var(--text-muted)]">API cost/hr</span>
          <span className="font-mono text-[20px] font-bold" style={{ color: model.accent, letterSpacing: "-0.02em" }}>
            {formatCost(cost)}/hr
          </span>
        </div>
        <Bar value={cost} maxValue={maxCost} color={model.accent} />
        <div className="font-mono text-[10px] text-[var(--text-muted)] mt-1">{(tokensPerHour / 1000).toFixed(0)}K tokens/hr</div>
      </div>

      {model.modalityPricing && (
        <div className="mt-3 pt-3 border-t border-[var(--border)]">
          <div className="font-mono text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">Modality pricing</div>
          <div className="flex gap-1.5 flex-wrap">
            {[{ label: "Text", price: model.pricePerMillionText, mods: ["text"] }, { label: "Image/Video", price: model.pricePerMillionImage, mods: ["image", "video", "screenshot"] }].map(({ label, price, mods }) => {
              const isActive = activeModality !== "all" && mods.includes(activeModality);
              return (
                <div key={label} className="font-mono text-[11px] px-2 py-1 rounded" style={{ background: isActive ? `${model.accent}15` : "var(--bg)", border: isActive ? `1px solid ${model.accent}` : "1px solid transparent", color: isActive ? model.accent : "var(--text-secondary)", fontWeight: isActive ? 600 : 400 }}>
                  {label}: <strong>${price}/1M</strong>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="font-mono text-[10px] text-[var(--text-muted)] mt-3">{model.hostingNote}</div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────
export default function EmbeddingCompare() {
  const [useCaseId, setUseCaseId] = useState("rag");
  const [docsPerHour, setDocsPerHour] = useState(10000);
  const [batchMode, setBatchMode] = useState(false);
  const [modalityFilter, setModalityFilter] = useState("all");

  const useCase = USE_CASES.find((u) => u.id === useCaseId);
  const tokensPerDoc = useCase.tokensPerDoc;
  const tokensPerHour = docsPerHour * tokensPerDoc;

  const costs = MODELS.map((m) => {
    const adj = batchMode && m.id === "gemini" && m.batchPrice != null ? { ...m, pricePerMillion: m.batchPrice } : m;
    const supported = modelSupportsModality(m, modalityFilter);
    const cost = supported ? calcCostPerHour(adj, docsPerHour, tokensPerDoc, modalityFilter) : null;
    return { model: m, cost, supported };
  });

  const supportedCosts = costs.filter((c) => c.supported).map((c) => c.cost);
  const maxCost = supportedCosts.length ? Math.max(...supportedCosts) : 1;
  const minCost = supportedCosts.length ? Math.min(...supportedCosts) : 0;

  const handleDocsChange = useCallback((e) => setDocsPerHour(parseInt(e.target.value)), []);
  const supportedCount = costs.filter((c) => c.supported).length;

  return (
    <div className="animate-slide-up">
      <div className="mb-6">
        <h2 className="text-[18px] font-semibold text-[var(--text-primary)]">Embedding Cost Comparison</h2>
        <p className="text-[12px] font-mono text-[var(--text-muted)] mt-1">
          Gemini Embedding 2 vs Qwen3-VL-Embedding vs Qwen3 Embedding 8B — prices as of April 2026
        </p>
      </div>

      {/* Controls */}
      <div className="panel p-5 mb-4 grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-5 items-end">
        <div>
          <label className="block font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-1.5">Use-case</label>
          <select value={useCaseId} onChange={(e) => setUseCaseId(e.target.value)} className="w-full text-[13px] p-2 border border-[var(--border-strong)] rounded-lg bg-[var(--panel)] text-[var(--text-primary)] cursor-pointer outline-none focus:border-[var(--accent)]">
            {USE_CASES.map((u) => <option key={u.id} value={u.id}>{u.name} — {u.chunkLabel}</option>)}
          </select>
          <p className="text-[11px] text-[var(--text-muted)] mt-1">{useCase.description}</p>
        </div>

        <div>
          <label className="block font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
            Docs/hr — <span className="text-[var(--text-primary)] font-bold">{docsPerHour.toLocaleString()}</span>
          </label>
          <input type="range" min={100} max={200000} step={100} value={docsPerHour} onChange={handleDocsChange} className="w-full" />
          <div className="flex justify-between font-mono text-[10px] text-[var(--text-muted)] mt-1">
            <span>100</span>
            <span>{(tokensPerHour / 1000).toFixed(0)}K tok/hr</span>
            <span>200K</span>
          </div>
        </div>

        <div className="pb-5">
          <label className="flex items-center gap-2 cursor-pointer text-[12px] text-[var(--text-secondary)] whitespace-nowrap font-medium">
            <div onClick={() => setBatchMode((b) => !b)} className="w-9 h-5 rounded-full relative cursor-pointer flex-shrink-0" style={{ background: batchMode ? "var(--accent)" : "var(--border-strong)", transition: "background 0.2s" }}>
              <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow" style={{ left: batchMode ? 18 : 2, transition: "left 0.2s" }} />
            </div>
            Gemini Batch (-50%)
          </label>
        </div>
      </div>

      {/* Modality filter */}
      <div className="panel p-4 mb-6">
        <div className="font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2.5">
          Filter by modality
          {modalityFilter !== "all" && supportedCount < MODELS.length && (
            <span className="ml-2 text-[10px] font-normal normal-case tracking-normal">{supportedCount}/{MODELS.length} models</span>
          )}
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {MODALITY_FILTERS.map((f) => {
            const count = f.id === "all" ? MODELS.length : MODELS.filter((m) => modelSupportsModality(m, f.id)).length;
            return (
              <button key={f.id} onClick={() => setModalityFilter(f.id)} className={`chip ${modalityFilter === f.id ? "active" : ""}`}>
                {f.label}
                <span className="text-[10px] font-semibold px-1 py-0 rounded-full" style={{ background: modalityFilter === f.id ? "rgba(255,255,255,0.2)" : "var(--bg)", color: modalityFilter === f.id ? "#fff" : "var(--text-muted)" }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Model cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {costs.map(({ model, cost, supported }) => (
          <ModelCard key={model.id} model={model} cost={cost} maxCost={maxCost} isLowest={supported && cost === minCost} tokensPerHour={tokensPerHour} activeModality={modalityFilter} supported={supported} />
        ))}
      </div>

      {/* Spec table */}
      <div className="panel overflow-hidden mb-5">
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <span className="font-mono text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Quick-reference spec table</span>
        </div>
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Modality</th>
                <th>Context</th>
                <th>Dims</th>
                <th>Price/1M</th>
                <th>Availability</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m) => (
                <tr key={m.id}>
                  <td className="font-medium whitespace-nowrap">
                    <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: m.accent }} />
                    {m.name}
                    {m.dtype && <span className="font-mono text-[9px] text-[var(--text-muted)] ml-1.5">{m.dtype}</span>}
                  </td>
                  <td className="text-[var(--text-secondary)]">{m.modality.join(", ")}</td>
                  <td className="font-mono whitespace-nowrap">{m.contextTokens.toLocaleString()} tok</td>
                  <td className="font-mono text-[11px]">{m.dims}</td>
                  <td className="font-mono whitespace-nowrap">
                    {m.id === "gemini" ? <><div>Text/PDF: $0.20</div><div>Image: $0.45</div><div>Audio: $6.50</div><div>Video: $12.00</div></> : m.id === "qwen-vl" ? <><div>Text: $0.10</div><div>Img/Vid: $0.258</div></> : `$${m.pricePerMillion}`}
                  </td>
                  <td className="text-[var(--text-secondary)]">{m.hostingNote}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer notes */}
      <div className="text-[11px] text-[var(--text-muted)] leading-relaxed border-t border-[var(--border)] pt-3 font-mono">
        Qwen3-VL-Embedding: $0.10/1M text, $0.258/1M image/video (DashScope). Dims 256–2560 (float32).
        Gemini Embedding 2: $0.20/1M text/PDF, $0.45/1M image, $6.50/1M audio, $12.00/1M video. Batch N/A for embeddings.
        Qwen3 Embedding 8B: $0.01/1M via OpenRouter.
      </div>
    </div>
  );
}
