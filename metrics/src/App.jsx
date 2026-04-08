import { useState, useMemo } from "react";

// ── Provider pricing ($/Mtok input) ──────────────────────────────
const PROVIDERS = [
  { id: "claude-haiku", name: "Claude 4.5 Haiku", input: 0.8, accent: "#c084fc", accentBg: "#2e1065" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", input: 0.15, accent: "#34d399", accentBg: "#022c22" },
  { id: "gemini-flash", name: "Gemini 2.5 Flash", input: 0.15, accent: "#60a5fa", accentBg: "#172554" },
  { id: "qwen-vl-72b", name: "Qwen3-VL 72B", input: 0.4, accent: "#f59e0b", accentBg: "#451a03" },
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

// ── Modality tabs ────────────────────────────────────────────────
const TABS = [
  { id: "video", label: "Video", icon: "▶" },
  { id: "audio", label: "Audio", icon: "♫" },
  { id: "pdf", label: "PDF", icon: "◈" },
  { id: "image", label: "Image", icon: "⬡" },
  { id: "overview", label: "Overview", icon: "≡" },
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

// ── Components ──────────────────────────────────────────────────

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function CostTable({ rows, columns, caption }) {
  return (
    <div className="overflow-x-auto">
      {caption && <div className="text-sm text-gray-400 mb-2">{caption}</div>}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`py-2 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${col.align === "right" ? "text-right" : "text-left"}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-900/50">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`py-2 px-3 ${col.align === "right" ? "text-right" : ""} ${col.style?.(row) || ""}`}
                >
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

// ── Video section ───────────────────────────────────────────────

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
    costPerHr: totalTokens * p.input / 1_000_000,
    costPerMin: (totalTokens * p.input / 1_000_000) / (duration / 60),
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${(duration / 60).toFixed(0)} min`} />
        <StatCard label="Keyframes" value={fmt(numKeyframes)} sub={`@ ${kfFps} kf/s`} />
        <StatCard label="Tok/frame" value={fmt(tokPerFrame)} sub={`${resolution} → ${Math.ceil(w / TILE_PX)}×${Math.ceil(h / TILE_PX)} tiles`} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
      </div>

      <div className="flex flex-wrap gap-4 items-center">
        <label className="text-sm text-gray-400">
          Duration (min):
          <input
            type="range" min={1} max={120} value={duration / 60}
            onChange={(e) => setDuration(Number(e.target.value) * 60)}
            className="ml-2 w-32 accent-indigo-500"
          />
          <span className="ml-2 text-white font-mono">{(duration / 60).toFixed(0)}</span>
        </label>

        <div className="flex gap-2">
          {Object.keys(resolutions).map((r) => (
            <button
              key={r}
              onClick={() => setResolution(r)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                resolution === r ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          {[0.5, 1.0, 2.0].map((f) => (
            <button
              key={f}
              onClick={() => setKfFps(f)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                kfFps === f ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {f} kf/s
            </button>
          ))}
        </div>
      </div>

      <CostTable
        caption="Cost per provider"
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }}>{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => fmt(r.tokens) },
          { key: "costPerHr", label: `$/${duration >= 3600 ? "hr" : (duration / 60).toFixed(0) + "min"}`, align: "right", render: (r) => <span className="text-green-400 font-mono">{fmtCost(r.costPerHr)}</span> },
          { key: "costPerMin", label: "$/min", align: "right", render: (r) => <span className="font-mono text-gray-400">{fmtCost(r.costPerMin)}</span> },
        ]}
      />
    </div>
  );
}

// ── Audio section ───────────────────────────────────────────────

function AudioSection() {
  const [duration, setDuration] = useState(3600);
  const totalTokens = Math.round(duration * TOKENS_PER_AUDIO_SECOND);

  const rows = PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens: totalTokens,
    costPerHr: totalTokens * p.input / 1_000_000,
    costPerMin: (totalTokens * p.input / 1_000_000) / (duration / 60),
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${(duration / 60).toFixed(0)} min`} />
        <StatCard label="Tok/second" value={TOKENS_PER_AUDIO_SECOND} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Cheapest $/hr" value={fmtCost(Math.min(...rows.map((r) => r.costPerHr)))} />
      </div>

      <label className="text-sm text-gray-400 flex items-center gap-2">
        Duration (min):
        <input
          type="range" min={1} max={120} value={duration / 60}
          onChange={(e) => setDuration(Number(e.target.value) * 60)}
          className="w-40 accent-indigo-500"
        />
        <span className="text-white font-mono">{(duration / 60).toFixed(0)}</span>
      </label>

      <CostTable
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }}>{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => fmt(r.tokens) },
          { key: "costPerHr", label: "$/hr", align: "right", render: (r) => <span className="text-green-400 font-mono">{fmtCost(r.costPerHr)}</span> },
          { key: "costPerMin", label: "$/min", align: "right", render: (r) => <span className="font-mono text-gray-400">{fmtCost(r.costPerMin)}</span> },
        ]}
      />
    </div>
  );
}

// ── PDF section ─────────────────────────────────────────────────

function PdfSection() {
  const [pages, setPages] = useState(100);
  const [charsPerPage, setCharsPerPage] = useState(CHARS_PER_PAGE);
  const totalChars = pages * charsPerPage;
  const totalTokens = Math.round(totalChars * TOKENS_PER_CHAR);

  const rows = PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens: totalTokens,
    costTotal: totalTokens * p.input / 1_000_000,
    costPerPage: (totalTokens * p.input / 1_000_000) / pages,
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pages" value={pages} />
        <StatCard label="Chars/page" value={fmt(charsPerPage)} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Tok/page" value={fmt(Math.round(totalTokens / pages))} />
      </div>

      <div className="flex flex-wrap gap-4 items-center">
        <label className="text-sm text-gray-400 flex items-center gap-2">
          Pages:
          <input
            type="range" min={1} max={500} value={pages}
            onChange={(e) => setPages(Number(e.target.value))}
            className="w-40 accent-indigo-500"
          />
          <span className="text-white font-mono">{pages}</span>
        </label>

        <div className="flex gap-2">
          {[1500, 3000, 5000].map((c) => (
            <button
              key={c}
              onClick={() => setCharsPerPage(c)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                charsPerPage === c ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {fmt(c)} chars/pg
            </button>
          ))}
        </div>
      </div>

      <CostTable
        rows={rows}
        columns={[
          { key: "provider", label: "Provider", render: (r) => <span style={{ color: r.accent }}>{r.provider}</span> },
          { key: "tokens", label: "Tokens", align: "right", render: (r) => fmt(r.tokens) },
          { key: "costTotal", label: `$/${pages}pg`, align: "right", render: (r) => <span className="text-green-400 font-mono">{fmtCost(r.costTotal)}</span> },
          { key: "costPerPage", label: "$/page", align: "right", render: (r) => <span className="font-mono text-gray-400">{fmtCost(r.costPerPage)}</span> },
        ]}
      />
    </div>
  );
}

// ── Image section ───────────────────────────────────────────────

function ImageSection() {
  const presets = [
    { name: "SD", w: 640, h: 480 },
    { name: "HD", w: 1280, h: 720 },
    { name: "Full HD", w: 1920, h: 1080 },
    { name: "4K", w: 3840, h: 2160 },
    { name: "8K", w: 7680, h: 4320 },
  ];

  const rows = [];
  for (const preset of presets) {
    const tokens = imageTokens(preset.w, preset.h);
    const tilesW = Math.ceil(preset.w / TILE_PX);
    const tilesH = Math.ceil(preset.h / TILE_PX);
    for (const p of PROVIDERS) {
      rows.push({
        resolution: `${preset.name} (${preset.w}x${preset.h})`,
        tiles: `${tilesW}x${tilesH}`,
        tokens,
        provider: p.name,
        accent: p.accent,
        cost: tokens * p.input / 1_000_000,
      });
    }
  }

  // Group by resolution for compact display
  const grouped = presets.map((preset) => {
    const tokens = imageTokens(preset.w, preset.h);
    const tilesW = Math.ceil(preset.w / TILE_PX);
    const tilesH = Math.ceil(preset.h / TILE_PX);
    return {
      name: preset.name,
      dims: `${preset.w}x${preset.h}`,
      tiles: `${tilesW}x${tilesH}`,
      tokens,
      costs: PROVIDERS.map((p) => ({
        name: p.name,
        accent: p.accent,
        cost: tokens * p.input / 1_000_000,
      })),
    };
  });

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="py-2 px-3 text-left text-xs font-medium text-gray-500 uppercase">Resolution</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-500 uppercase">Tiles</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-500 uppercase">Tokens</th>
              {PROVIDERS.map((p) => (
                <th key={p.id} className="py-2 px-3 text-right text-xs font-medium text-gray-500 uppercase" style={{ color: p.accent }}>
                  {p.name.split(" ").slice(-1)[0]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grouped.map((g) => (
              <tr key={g.name} className="border-b border-gray-800/50 hover:bg-gray-900/50">
                <td className="py-2 px-3 font-medium">{g.name} <span className="text-gray-500 text-xs">{g.dims}</span></td>
                <td className="py-2 px-3 text-right text-gray-400">{g.tiles}</td>
                <td className="py-2 px-3 text-right font-mono text-cyan-400">{fmt(g.tokens)}</td>
                {g.costs.map((c, i) => (
                  <td key={i} className="py-2 px-3 text-right font-mono text-gray-400">{fmtCost(c.cost)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Overview section ────────────────────────────────────────────

function OverviewSection() {
  const scenarios = [
    { label: "1 image (1080p)", tokens: imageTokens(1920, 1080), unit: "/image" },
    { label: "1 min audio", tokens: 60 * TOKENS_PER_AUDIO_SECOND, unit: "/min" },
    { label: "1 min video (1080p, 1kf/s)", tokens: 60 * imageTokens(1920, 1080), unit: "/min" },
    { label: "10 pages PDF", tokens: Math.round(10 * CHARS_PER_PAGE * TOKENS_PER_CHAR), unit: "/10pg" },
    { label: "1 hr audio", tokens: 3600 * TOKENS_PER_AUDIO_SECOND, unit: "/hr" },
    { label: "1 hr video (1080p, 1kf/s)", tokens: 3600 * imageTokens(1920, 1080), unit: "/hr" },
    { label: "100 pages PDF", tokens: Math.round(100 * CHARS_PER_PAGE * TOKENS_PER_CHAR), unit: "/100pg" },
  ];

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="py-2 px-3 text-left text-xs font-medium text-gray-500 uppercase">Scenario</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-500 uppercase">Tokens</th>
              {PROVIDERS.map((p) => (
                <th key={p.id} className="py-2 px-3 text-right text-xs font-medium uppercase" style={{ color: p.accent }}>
                  {p.name.split(" ").slice(-1)[0]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.label} className="border-b border-gray-800/50 hover:bg-gray-900/50">
                <td className="py-2 px-3">{s.label}</td>
                <td className="py-2 px-3 text-right font-mono text-cyan-400">{fmt(s.tokens)}</td>
                {PROVIDERS.map((p) => (
                  <td key={p.id} className="py-2 px-3 text-right font-mono text-gray-400">
                    {fmtCost(s.tokens * p.input / 1_000_000)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-xs text-gray-500 space-y-1">
        <div><strong>Token estimation rules:</strong></div>
        <div>Image: {TOKENS_PER_IMAGE_BASE} base + {TOKENS_PER_TILE} per {TILE_PX}x{TILE_PX} tile</div>
        <div>Audio: {TOKENS_PER_AUDIO_SECOND} tokens/second</div>
        <div>Video: keyframe extraction at configurable rate, each frame treated as image</div>
        <div>PDF: ~{TOKENS_PER_CHAR} tokens/char, ~{CHARS_PER_PAGE} chars/page average</div>
      </div>
    </div>
  );
}

// ── App ─────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("video");

  return (
    <div className="min-h-screen bg-gray-950">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">
              mm <span className="text-indigo-400">metrics</span>
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Multi-modal context cost &amp; performance calculator
            </p>
          </div>
          <div className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                  tab === t.id
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                <span className="mr-1">{t.icon}</span>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {tab === "video" && <VideoSection />}
        {tab === "audio" && <AudioSection />}
        {tab === "pdf" && <PdfSection />}
        {tab === "image" && <ImageSection />}
        {tab === "overview" && <OverviewSection />}
      </main>

      <footer className="border-t border-gray-800 px-6 py-3 text-center text-xs text-gray-600">
        mm v0.3.0 — token estimates are approximate
      </footer>
    </div>
  );
}
