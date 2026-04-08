import { useState } from "react";
import StatCard from "../components/StatCard";
import CostTable from "../components/CostTable";
import { Slider, ChipGroup } from "../components/Controls";
import { fmt, fmtCost } from "../lib/format";
import PROVIDERS, { cost } from "../lib/providers";
import {
  imageTokens,
  TOKENS_PER_IMAGE_BASE,
  TOKENS_PER_TILE,
  TILE_PX,
  TOKENS_PER_AUDIO_SECOND,
  CHARS_PER_PAGE,
  TOKENS_PER_CHAR,
} from "../lib/tokens";

// ── Tabs ─────────────────────────────────────────────────────────

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "video", label: "Video" },
  { value: "audio", label: "Audio" },
  { value: "pdf", label: "PDF" },
  { value: "image", label: "Image" },
];

// ── Helpers ──────────────────────────────────────────────────────

const RESOLUTIONS = {
  "720p": [1280, 720],
  "1080p": [1920, 1080],
  "4K": [3840, 2160],
};

function providerRows(tokens, perUnit) {
  return PROVIDERS.map((p) => ({
    provider: p.name,
    accent: p.accent,
    tokens,
    total: cost(tokens, p),
    rate: cost(tokens, p) / perUnit,
  }));
}

// ── Sections ─────────────────────────────────────────────────────

function VideoSection() {
  const [minutes, setMinutes] = useState(60);
  const [resolution, setResolution] = useState("1080p");
  const [kfFps, setKfFps] = useState(1.0);

  const [w, h] = RESOLUTIONS[resolution];
  const tokPerFrame = imageTokens(w, h);
  const numKeyframes = Math.round(minutes * 60 * kfFps);
  const totalTokens = numKeyframes * tokPerFrame;

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${minutes} min`} />
        <StatCard label="Keyframes" value={fmt(numKeyframes)} sub={`@ ${kfFps} kf/s`} />
        <StatCard label="Tok/frame" value={fmt(tokPerFrame)} sub={`${resolution} — ${Math.ceil(w / TILE_PX)}x${Math.ceil(h / TILE_PX)} tiles`} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
      </div>

      <div className="panel p-4 flex flex-wrap gap-4 items-center">
        <Slider label="Duration" min={1} max={120} value={minutes} onChange={setMinutes} suffix="m" />
        <ChipGroup options={Object.keys(RESOLUTIONS)} value={resolution} onChange={setResolution} />
        <ChipGroup
          options={[0.5, 1.0, 2.0].map((f) => ({ value: f, label: `${f} kf/s` }))}
          value={kfFps}
          onChange={setKfFps}
        />
      </div>

      <CostTable rows={providerRows(totalTokens, minutes)} unitLabel="$/min" />
    </div>
  );
}

function AudioSection() {
  const [minutes, setMinutes] = useState(60);
  const totalTokens = Math.round(minutes * 60 * TOKENS_PER_AUDIO_SECOND);
  const rows = providerRows(totalTokens, minutes);

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Duration" value={`${minutes} min`} />
        <StatCard label="Tok/second" value={TOKENS_PER_AUDIO_SECOND} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Cheapest $/min" value={fmtCost(Math.min(...rows.map((r) => r.rate)))} />
      </div>

      <div className="panel p-4">
        <Slider label="Duration" min={1} max={120} value={minutes} onChange={setMinutes} suffix="m" />
      </div>

      <CostTable rows={rows} unitLabel="$/min" />
    </div>
  );
}

function PdfSection() {
  const [pages, setPages] = useState(100);
  const [charsPerPage, setCharsPerPage] = useState(CHARS_PER_PAGE);
  const totalTokens = Math.round(pages * charsPerPage * TOKENS_PER_CHAR);

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pages" value={pages} />
        <StatCard label="Chars/page" value={fmt(charsPerPage)} />
        <StatCard label="Total tokens" value={fmt(totalTokens)} />
        <StatCard label="Tok/page" value={fmt(Math.round(totalTokens / pages))} />
      </div>

      <div className="panel p-4 flex flex-wrap gap-4 items-center">
        <Slider label="Pages" min={1} max={500} value={pages} onChange={setPages} />
        <ChipGroup
          options={[1500, 3000, 5000].map((c) => ({ value: c, label: `${fmt(c)} ch/pg` }))}
          value={charsPerPage}
          onChange={setCharsPerPage}
        />
      </div>

      <CostTable rows={providerRows(totalTokens, pages)} unitLabel="$/page" />
    </div>
  );
}

function ImageSection() {
  const presets = [
    { name: "SD", w: 640, h: 480 },
    { name: "HD", w: 1280, h: 720 },
    { name: "Full HD", w: 1920, h: 1080 },
    { name: "4K", w: 3840, h: 2160 },
    { name: "8K", w: 7680, h: 4320 },
  ];

  const grouped = presets.map((p) => {
    const tokens = imageTokens(p.w, p.h);
    return {
      name: p.name,
      dims: `${p.w}x${p.h}`,
      tiles: `${Math.ceil(p.w / TILE_PX)}x${Math.ceil(p.h / TILE_PX)}`,
      tokens,
      costs: PROVIDERS.map((prov) => ({ accent: prov.accent, cost: cost(tokens, prov) })),
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
              <th key={p.id} className="text-right" style={{ color: p.accent }}>
                {p.name.split(" ").slice(-1)[0]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grouped.map((g) => (
            <tr key={g.name}>
              <td className="font-medium">
                {g.name} <span className="text-[var(--text-muted)] text-[11px] font-mono">{g.dims}</span>
              </td>
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
                <th key={p.id} className="text-right" style={{ color: p.accent }}>
                  {p.name.split(" ").slice(-1)[0]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.label}>
                <td>{s.label}</td>
                <td className="text-right font-mono font-semibold" style={{ color: "var(--accent)" }}>{fmt(s.tokens)}</td>
                {PROVIDERS.map((p) => (
                  <td key={p.id} className="text-right font-mono text-[var(--text-secondary)]">
                    {fmtCost(cost(s.tokens, p))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel p-4 space-y-1">
        <div className="font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
          Token estimation rules
        </div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">
          Image: {TOKENS_PER_IMAGE_BASE} base + {TOKENS_PER_TILE} per {TILE_PX}x{TILE_PX} tile
        </div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">
          Audio: {TOKENS_PER_AUDIO_SECOND} tokens/second
        </div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">
          Video: keyframe extraction at configurable rate, each frame = image
        </div>
        <div className="text-[12px] text-[var(--text-secondary)] font-mono">
          PDF: ~{TOKENS_PER_CHAR} tokens/char, ~{CHARS_PER_PAGE} chars/page avg
        </div>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────

export default function TokenCost() {
  const [tab, setTab] = useState("overview");

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-[18px] font-semibold text-[var(--text-primary)]">Token Cost Calculator</h2>
        <p className="text-[12px] font-mono text-[var(--text-muted)] mt-1">
          Multi-modal context cost estimates by provider and modality
        </p>
      </div>

      <div className="flex gap-1 mb-6">
        <ChipGroup options={TABS} value={tab} onChange={setTab} />
      </div>

      {tab === "video" && <VideoSection />}
      {tab === "audio" && <AudioSection />}
      {tab === "pdf" && <PdfSection />}
      {tab === "image" && <ImageSection />}
      {tab === "overview" && <OverviewSection />}
    </div>
  );
}
