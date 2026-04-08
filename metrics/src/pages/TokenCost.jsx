import { useState } from "react";

// ── Provider pricing ($/Mtok input) ──────────────────────────────
const PROVIDERS = [
  { id: "claude-haiku", name: "Claude 4.5 Haiku", input: 0.8, accent: "#8b5cf6" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", input: 0.15, accent: "#10b981" },
  { id: "gemini-flash", name: "Gemini 2.5 Flash", input: 0.15, accent: "#3b82f6" },
  { id: "qwen-vl-72b", name: "Qwen3-VL 72B", input: 0.4, accent: "#f59e0b" },
];

// ── Token estimation constants ───────────────────────────────────
const TOKENS_PER_IMAGE_BASE = 85;
const TOKENS_PER_TILE = 170;
const TILE_PX = 512;
const TOKENS_PER_AUDIO_SECOND = 25;
const CHARS_PER_PAGE = 3000;
const TOKENS_PER_CHAR = 0.75;

function imageTokens(w, h) {
  const tw = Math.max(1, Math.ceil(w / TILE_PX));
  const th = Math.max(1, Math.ceil(h / TILE_PX));
  return TOKENS_PER_IMAGE_BASE + tw * th * TOKENS_PER_TILE;
}

// ── Tabs ─────────────────────────────────────────────────────────
const TABS = [
  { id: "video", label: "Video" },
  { id: "audio", label: "Audio" },
  { id: "pdf", label: "PDF" },
  { id: "image", label: "Image" },
  { id: "overview", label: "Overview" },
];

// ── Helpers ──────────────────────────────────────────────────────
function fmt(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function fmtCost(c) {
  if (c === 0) return "$0";
  if (c < 0.0001) return `$${c.toFixed(6)}`;
  if (c < 0.01) return `$${c.toFixed(4)}`;
  if (c < 1) return `$${c.toFixed(3)}`;
  return `$${c.toFixed(2)}`;
}

// ── Shared components ────────────────────────────────────────────

function StatCard({ label, value, sub }) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function CostTable({ rows, columns, caption }) {
  return (
    <div className="panel overflow-x-auto animate-slide-up">
      {caption && (
        <div className="px-4 py-2 border-b border-[var(--border)]">
          <span className="font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">{caption}</span>
        </div>
      )}
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={col.align === "right" ? "text-right" : ""}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col.key} className={col.align === "right" ? "text-right" : ""}>
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Video ────────────────────────────────────────────────────────

function VideoSection() {
  const [duration, setDuration] = useState(3600);
  const [resolution, setResolution] = useState("1080p");
  const [kfFps, setKfFps] = useState(1.0);

  const resolutions = { "720p": [1280, 720], "1080p": [1920, 1080], "4K": [3840, 2160] };
  const [w, h] = resolutions[resolution];
  const tokPerFrame = imageTokens(w, h);
  const numKeyframes = Math.round(duration * kfFps);
  const totalTokens = numKeyframes * tokPerFrame;

  const rows = PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens: totalTokens,
    costPerHr: (totalTokens * p.input) / 1_000_000,
    costPerMin: (totalTokens * p.input) / 1_000_000 / (duration / 60),
  }));

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${(duration / 60).toFixed(0)} min`} />
        <StatCard label="Keyframes" value={fmt(numKeyframes)} sub={`@ ${kfFps} kf/s`} />
        <StatCard label="Tok/frame" value={fmt(tokPerFrame)} sub={`${resolution} — ${Math.ceil(w / TILE_PX)}x${Math.ceil(h / TILE_PX)} tiles`} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
      </div>

      <div className="panel p-4 flex flex-wrap gap-4 items-center">
        <label className="text-[13px] text-[var(--text-secondary)] font-medium flex items-center gap-2">
          Duration
          <input type="range" min={1} max={120} value={duration / 60} onChange={(e) => setDuration(Number(e.target.value) * 60)} className="w-32" />
          <span className="font-mono text-[var(--text-primary)] font-semibold">{(duration / 60).toFixed(0)}m</span>
        </label>
        <div className="flex gap-1">
          {Object.keys(resolutions).map((r) => (
            <button key={r} onClick={() => setResolution(r)} className={`chip ${resolution === r ? "active" : ""}`}>{r}</button>
          ))}
        </div>
        <div className="flex gap-1">
          {[0.5, 1.0, 2.0].map((f) => (
            <button key={f} onClick={() => setKfFps(f)} className={`chip ${kfFps === f ? "active" : ""}`}>{f} kf/s</button>
          ))}
        </div>
      </div>

      <CostTable
        caption="Cost per provider"
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }} className="font-medium">{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => <span className="font-mono">{fmt(r.tokens)}</span> },
          { key: "costPerHr", label: `$/${duration >= 3600 ? "hr" : (duration / 60).toFixed(0) + "min"}`, align: "right", render: (r) => <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmtCost(r.costPerHr)}</span> },
          { key: "costPerMin", label: "$/min", align: "right", render: (r) => <span className="font-mono text-[var(--text-muted)]">{fmtCost(r.costPerMin)}</span> },
        ]}
      />
    </div>
  );
}

// ── Audio ────────────────────────────────────────────────────────

function AudioSection() {
  const [duration, setDuration] = useState(3600);
  const totalTokens = Math.round(duration * TOKENS_PER_AUDIO_SECOND);

  const rows = PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens: totalTokens,
    costPerHr: (totalTokens * p.input) / 1_000_000,
    costPerMin: (totalTokens * p.input) / 1_000_000 / (duration / 60),
  }));

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${(duration / 60).toFixed(0)} min`} />
        <StatCard label="Tok/second" value={TOKENS_PER_AUDIO_SECOND} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Cheapest $/hr" value={fmtCost(Math.min(...rows.map((r) => r.costPerHr)))} />
      </div>

      <div className="panel p-4">
        <label className="text-[13px] text-[var(--text-secondary)] font-medium flex items-center gap-2">
          Duration
          <input type="range" min={1} max={120} value={duration / 60} onChange={(e) => setDuration(Number(e.target.value) * 60)} className="w-40" />
          <span className="font-mono text-[var(--text-primary)] font-semibold">{(duration / 60).toFixed(0)}m</span>
        </label>
      </div>

      <CostTable
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }} className="font-medium">{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => <span className="font-mono">{fmt(r.tokens)}</span> },
          { key: "costPerHr", label: "$/hr", align: "right", render: (r) => <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmtCost(r.costPerHr)}</span> },
          { key: "costPerMin", label: "$/min", align: "right", render: (r) => <span className="font-mono text-[var(--text-muted)]">{fmtCost(r.costPerMin)}</span> },
        ]}
      />
    </div>
  );
}

// ── PDF ──────────────────────────────────────────────────────────

function PdfSection() {
  const [pages, setPages] = useState(100);
  const [charsPerPage, setCharsPerPage] = useState(CHARS_PER_PAGE);
  const totalChars = pages * charsPerPage;
  const totalTokens = Math.round(totalChars * TOKENS_PER_CHAR);

  const rows = PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens: totalTokens,
    costTotal: (totalTokens * p.input) / 1_000_000,
    costPerPage: (totalTokens * p.input) / 1_000_000 / pages,
  }));

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pages" value={pages} />
        <StatCard label="Chars/page" value={fmt(charsPerPage)} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Tok/page" value={fmt(Math.round(totalTokens / pages))} />
      </div>

      <div className="panel p-4 flex flex-wrap gap-4 items-center">
        <label className="text-[13px] text-[var(--text-secondary)] font-medium flex items-center gap-2">
          Pages
          <input type="range" min={1} max={500} value={pages} onChange={(e) => setPages(Number(e.target.value))} className="w-40" />
          <span className="font-mono text-[var(--text-primary)] font-semibold">{pages}</span>
        </label>
        <div className="flex gap-1">
          {[1500, 3000, 5000].map((c) => (
            <button key={c} onClick={() => setCharsPerPage(c)} className={`chip ${charsPerPage === c ? "active" : ""}`}>{fmt(c)} ch/pg</button>
          ))}
        </div>
      </div>

      <CostTable
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }} className="font-medium">{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => <span className="font-mono">{fmt(r.tokens)}</span> },
          { key: "costTotal", label: `$/${pages}pg`, align: "right", render: (r) => <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmtCost(r.costTotal)}</span> },
          { key: "costPerPage", label: "$/page", align: "right", render: (r) => <span className="font-mono text-[var(--text-muted)]">{fmtCost(r.costPerPage)}</span> },
        ]}
      />
    </div>
  );
}

// ── Image ────────────────────────────────────────────────────────

function ImageSection() {
  const presets = [
    { name: "SD", w: 640, h: 480 },
    { name: "HD", w: 1280, h: 720 },
    { name: "Full HD", w: 1920, h: 1080 },
    { name: "4K", w: 3840, h: 2160 },
    { name: "8K", w: 7680, h: 4320 },
  ];

  const grouped = presets.map((preset) => {
    const tokens = imageTokens(preset.w, preset.h);
    const tilesW = Math.ceil(preset.w / TILE_PX);
    const tilesH = Math.ceil(preset.h / TILE_PX);
    return {
      name: preset.name,
      dims: `${preset.w}x${preset.h}`,
      tiles: `${tilesW}x${tilesH}`,
      tokens,
      costs: PROVIDERS.map((p) => ({ name: p.name, accent: p.accent, cost: (tokens * p.input) / 1_000_000 })),
    };
  });

  return (
    <div className="panel overflow-x-auto animate-slide-up">
      <table>
        <thead>
          <tr>
            <th>Resolution</th>
            <th className="text-right">Tiles</th>
            <th className="text-right">Tokens</th>
            {PROVIDERS.map((p) => (
              <th key={p.id} className="text-right" style={{ color: p.accent }}>{p.name.split(" ").slice(-1)[0]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grouped.map((g) => (
            <tr key={g.name}>
              <td className="font-medium">{g.name} <span className="text-[var(--text-muted)] text-[11px] font-mono">{g.dims}</span></td>
              <td className="text-right font-mono text-[var(--text-muted)]">{g.tiles}</td>
              <td className="text-right font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmt(g.tokens)}</td>
              {g.costs.map((c, i) => (
                <td key={i} className="text-right font-mono text-[var(--text-secondary)]">{fmtCost(c.cost)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Overview ─────────────────────────────────────────────────────

function OverviewSection() {
  const scenarios = [
    { label: "1 image (1080p)", tokens: imageTokens(1920, 1080) },
    { label: "1 min audio", tokens: 60 * TOKENS_PER_AUDIO_SECOND },
    { label: "1 min video (1080p, 1kf/s)", tokens: 60 * imageTokens(1920, 1080) },
    { label: "10 pages PDF", tokens: Math.round(10 * CHARS_PER_PAGE * TOKENS_PER_CHAR) },
    { label: "1 hr audio", tokens: 3600 * TOKENS_PER_AUDIO_SECOND },
    { label: "1 hr video (1080p, 1kf/s)", tokens: 3600 * imageTokens(1920, 1080) },
    { label: "100 pages PDF", tokens: Math.round(100 * CHARS_PER_PAGE * TOKENS_PER_CHAR) },
  ];

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="panel overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th className="text-right">Tokens</th>
              {PROVIDERS.map((p) => (
                <th key={p.id} className="text-right" style={{ color: p.accent }}>{p.name.split(" ").slice(-1)[0]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.label}>
                <td>{s.label}</td>
                <td className="text-right font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmt(s.tokens)}</td>
                {PROVIDERS.map((p) => (
                  <td key={p.id} className="text-right font-mono text-[var(--text-secondary)]">{fmtCost((s.tokens * p.input) / 1_000_000)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel p-4 space-y-1">
        <div className="font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">Token estimation rules</div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">Image: {TOKENS_PER_IMAGE_BASE} base + {TOKENS_PER_TILE} per {TILE_PX}x{TILE_PX} tile</div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">Audio: {TOKENS_PER_AUDIO_SECOND} tokens/second</div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">Video: keyframe extraction at configurable rate, each frame = image</div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">PDF: ~{TOKENS_PER_CHAR} tokens/char, ~{CHARS_PER_PAGE} chars/page avg</div>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────

export default function TokenCost() {
  const [tab, setTab] = useState("video");

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-[18px] font-semibold text-[var(--text-primary)]">Token Cost Calculator</h2>
        <p className="text-[12px] font-mono text-[var(--text-muted)] mt-1">Multi-modal context cost estimates by provider and modality</p>
      </div>

      <div className="flex gap-1 mb-6">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`chip ${tab === t.id ? "active" : ""}`}>{t.label}</button>
        ))}
      </div>

      {tab === "video" && <VideoSection />}
      {tab === "audio" && <AudioSection />}
      {tab === "pdf" && <PdfSection />}
      {tab === "image" && <ImageSection />}
      {tab === "overview" && <OverviewSection />}
    </div>
  );
}
