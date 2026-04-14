const ASCII = `███╗   ███╗███╗   ███╗
████╗ ████║████╗ ████║
██╔████╔██║██╔████╔██║
██║╚██╔╝██║██║╚██╔╝██║
██║ ╚═╝ ██║██║ ╚═╝ ██║
╚═╝     ╚═╝╚═╝     ╚═╝`;

function FeatureCard({ icon, name, desc }) {
  return (
    <div className="panel p-4 text-center">
      <div className="text-xl mb-1">{icon}</div>
      <div className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)] mb-1">
        {name}
      </div>
      <div className="text-[12px] text-[var(--text-secondary)] leading-relaxed">
        {desc}
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="animate-slide-up flex flex-col items-center gap-8">
      {/* ASCII + tagline */}
      <div className="text-center">
        <pre className="font-mono text-[clamp(0.5rem,1.5vw,1rem)] leading-tight text-[var(--accent)] font-bold whitespace-pre">
          {ASCII}
        </pre>
        <p className="mt-2 text-[14px] text-[var(--text-secondary)] tracking-wide">
          <span className="font-semibold text-[var(--text-primary)]">
            High-performance multi-modal context
          </span>{" "}
          for humans & agents
        </p>
      </div>

      {/* Diagram */}
      <div className="w-full max-w-[760px]">
        <svg
          viewBox="0 0 700 250"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          className="w-full h-auto"
        >
          <defs>
            <linearGradient id="g-accent" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#06b6d4" />
              <stop offset="100%" stopColor="#0891b2" />
            </linearGradient>
            <linearGradient id="g-flow" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.02" />
            </linearGradient>
            <marker
              id="arrow"
              viewBox="0 0 10 7"
              refX="10"
              refY="3.5"
              markerWidth="8"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,3.5 L0,7" fill="#06b6d4" opacity="0.6" />
            </marker>
          </defs>

          {/* Background */}
          <rect
            x="0"
            y="10"
            width="700"
            height="220"
            rx="12"
            fill="url(#g-flow)"
          />

          {/* Sources */}
          <rect
            x="18"
            y="40"
            width="120"
            height="160"
            rx="8"
            fill="var(--panel)"
            stroke="var(--border)"
          />
          <text
            x="78"
            y="60"
            textAnchor="middle"
            fill="#06b6d4"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
            letterSpacing="0.1em"
          >
            SOURCES
          </text>
          <line x1="30" y1="68" x2="126" y2="68" stroke="var(--border)" />
          {[
            ["34", "88", "◈", "PDF"],
            ["34", "108", "⬡", "Image"],
            ["34", "128", "▶", "Video"],
            ["34", "148", "♫", "Audio"],
            ["34", "168", "T", "Text"],
          ].map(([x, y, icon, label]) => (
            <g key={label}>
              <text
                x={x}
                y={y}
                fill="var(--text-primary)"
                fontSize="12"
                fontFamily="var(--font-mono)"
              >
                {icon}
              </text>
              <text
                x="50"
                y={y}
                fill="var(--text-secondary)"
                fontSize="10"
                fontFamily="var(--font-mono)"
              >
                {label}
              </text>
            </g>
          ))}
          <text
            x="34"
            y="188"
            fill="var(--text-muted)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            …
          </text>
          <text
            x="46"
            y="188"
            fill="var(--text-muted)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            and more
          </text>

          {/* Arrow: Sources → mm */}
          <line
            x1="143"
            y1="120"
            x2="182"
            y2="120"
            stroke="#06b6d4"
            strokeOpacity="0.5"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />

          {/* mm box */}
          <rect
            x="188"
            y="22"
            width="320"
            height="196"
            rx="8"
            fill="var(--panel)"
            stroke="url(#g-accent)"
            strokeWidth="1.5"
          />
          <text
            x="348"
            y="44"
            textAnchor="middle"
            fill="url(#g-accent)"
            fontSize="13"
            fontWeight="700"
            fontFamily="var(--font-mono)"
            letterSpacing="0.12em"
          >
            mm
          </text>
          <line x1="202" y1="52" x2="494" y2="52" stroke="var(--border)" />

          {/* Context sub-block */}
          <rect
            x="204"
            y="66"
            width="290"
            height="60"
            rx="5"
            fill="var(--bg)"
            stroke="var(--border)"
          />
          <text
            x="218"
            y="90"
            fill="#06b6d4"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            Context
          </text>
          <text
            x="218"
            y="108"
            fill="var(--text-muted)"
            fontSize="8.5"
            fontFamily="var(--font-mono)"
          >
            hash · kind · text · codecs · pages · duration
          </text>

          {/* Semantic sub-block */}
          <rect
            x="204"
            y="142"
            width="290"
            height="60"
            rx="5"
            fill="var(--bg)"
            stroke="var(--border)"
          />
          <text
            x="218"
            y="166"
            fill="#06b6d4"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            Semantic
          </text>
          <text
            x="218"
            y="184"
            fill="var(--text-muted)"
            fontSize="8.5"
            fontFamily="var(--font-mono)"
          >
            captions · embeddings · analysis · search · encoders
          </text>

          {/* Arrows: mm → Consumers */}
          <line
            x1="513"
            y1="100"
            x2="560"
            y2="84"
            stroke="#06b6d4"
            strokeOpacity="0.5"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />
          <line
            x1="513"
            y1="140"
            x2="560"
            y2="156"
            stroke="#06b6d4"
            strokeOpacity="0.5"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />

          {/* Consumers */}
          <rect
            x="565"
            y="57"
            width="115"
            height="54"
            rx="6"
            fill="var(--panel)"
            stroke="var(--border)"
          />
          <text
            x="622"
            y="82"
            textAnchor="middle"
            fill="var(--text-primary)"
            fontSize="20"
          >
            🧑‍💻
          </text>
          <text
            x="622"
            y="101"
            textAnchor="middle"
            fill="var(--text-secondary)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            Humans
          </text>

          <rect
            x="565"
            y="129"
            width="115"
            height="54"
            rx="6"
            fill="var(--panel)"
            stroke="var(--border)"
          />
          <text
            x="622"
            y="154"
            textAnchor="middle"
            fill="var(--text-primary)"
            fontSize="20"
          >
            🤖
          </text>
          <text
            x="622"
            y="173"
            textAnchor="middle"
            fill="var(--text-secondary)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            Agents
          </text>

          {/* Tech strip */}
          <text
            x="350"
            y="242"
            textAnchor="middle"
            fontFamily="var(--font-mono)"
            fontSize="9"
            fill="var(--text-muted)"
            letterSpacing="0.06em"
          >
            Rust core · Arrow IPC · zero-copy · gitignore-aware · pipe-native
          </text>
        </svg>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-3 gap-3 w-full max-w-[760px]">
        <FeatureCard
          icon="⚡"
          name="Fast"
          desc="Rust core, rayon parallelism. Extremely fast."
        />
        <FeatureCard
          icon="🔍"
          name="Multimodal"
          desc="Multimodal awareness for find · cat · grep"
        />
        <FeatureCard
          icon="🔗"
          name="Composable"
          desc="Pipes, Arrow, DataFrames. CLI + Python API."
        />
      </div>

      {/* Install */}
      <div className="font-mono text-[12px] text-[var(--text-muted)]">
        <code className="bg-[var(--panel)] border border-[var(--border)] rounded px-2 py-1 text-[var(--text-secondary)]">
          pip install mm
        </code>
        <span className="mx-2">·</span>
        Rust + Python · Apache 2.0
      </div>
    </div>
  );
}
