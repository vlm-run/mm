import GettingStarted from "./GettingStarted";

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
      <div
        className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] mb-1"
        style={{ color: "var(--forest)" }}
      >
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
    <div className="animate-slide-up max-w-3xl mx-auto flex flex-col items-center gap-8">
      {/* ASCII + tagline */}
      <div className="text-center">
        <pre
          className="font-mono text-[clamp(0.5rem,1.5vw,1rem)] leading-tight font-bold whitespace-pre"
          style={{ color: "var(--forest)" }}
        >
          {ASCII}
        </pre>
        <p className="mt-3 text-[17px] tracking-wide">
          <span
            className="font-semibold"
            style={{
              fontFamily: "var(--font-heading)",
              color: "var(--forest)",
            }}
          >
            Fast, multi-modal file intelligence for agents.
          </span>
        </p>
        <p className="mt-1.5 text-[13px] text-[var(--text-secondary)] tracking-wide font-mono">
          find · cat · grep — rebuilt for the multimodal era.
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
            <marker
              id="arrow"
              viewBox="0 0 10 7"
              refX="10"
              refY="3.5"
              markerWidth="8"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,3.5 L0,7" fill="#1A3C2B" opacity="0.5" />
            </marker>
          </defs>

          {/* Background */}
          <rect
            x="0"
            y="10"
            width="700"
            height="220"
            rx="2"
            fill="rgba(26,60,43,0.03)"
          />

          {/* Sources */}
          <rect
            x="18"
            y="40"
            width="120"
            height="160"
            rx="2"
            fill="#ffffff"
            stroke="rgba(58,58,56,0.2)"
          />
          <text
            x="78"
            y="60"
            textAnchor="middle"
            fill="#1A3C2B"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
            letterSpacing="0.1em"
          >
            SOURCES
          </text>
          <line
            x1="30"
            y1="68"
            x2="126"
            y2="68"
            stroke="rgba(58,58,56,0.2)"
          />
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
                fill="#1A3C2B"
                fontSize="12"
                fontFamily="var(--font-mono)"
              >
                {icon}
              </text>
              <text
                x="50"
                y={y}
                fill="#3A3A38"
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
            fill="rgba(58,58,56,0.5)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            …
          </text>
          <text
            x="46"
            y="188"
            fill="rgba(58,58,56,0.5)"
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
            stroke="#1A3C2B"
            strokeOpacity="0.4"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />

          {/* mm box */}
          <rect
            x="188"
            y="22"
            width="320"
            height="196"
            rx="2"
            fill="#ffffff"
            stroke="#1A3C2B"
            strokeWidth="1"
          />
          <text
            x="348"
            y="44"
            textAnchor="middle"
            fill="#1A3C2B"
            fontSize="13"
            fontWeight="700"
            fontFamily="var(--font-mono)"
            letterSpacing="0.12em"
          >
            mm
          </text>
          <line
            x1="202"
            y1="52"
            x2="494"
            y2="52"
            stroke="rgba(58,58,56,0.2)"
          />

          {/* Context sub-block */}
          <rect
            x="204"
            y="66"
            width="290"
            height="60"
            rx="2"
            fill="#F7F7F5"
            stroke="rgba(58,58,56,0.2)"
          />
          <text
            x="218"
            y="90"
            fill="#1A3C2B"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            Context
          </text>
          <text
            x="218"
            y="108"
            fill="rgba(58,58,56,0.5)"
            fontSize="8.5"
            fontFamily="var(--font-mono)"
          >
            hash · kind · text · pages · duration · dimensions
          </text>

          {/* Semantic sub-block */}
          <rect
            x="204"
            y="142"
            width="290"
            height="60"
            rx="2"
            fill="#F7F7F5"
            stroke="rgba(58,58,56,0.2)"
          />
          <text
            x="218"
            y="166"
            fill="#1A3C2B"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            Semantic
          </text>
          <text
            x="218"
            y="184"
            fill="rgba(58,58,56,0.5)"
            fontSize="8.5"
            fontFamily="var(--font-mono)"
          >
            captions · embeddings · search · encoders · pipelines
          </text>

          {/* Arrows: mm → Consumers */}
          <line
            x1="513"
            y1="100"
            x2="560"
            y2="84"
            stroke="#1A3C2B"
            strokeOpacity="0.4"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />
          <line
            x1="513"
            y1="140"
            x2="560"
            y2="156"
            stroke="#1A3C2B"
            strokeOpacity="0.4"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />

          {/* Consumers */}
          <rect
            x="565"
            y="57"
            width="115"
            height="54"
            rx="2"
            fill="#ffffff"
            stroke="rgba(58,58,56,0.2)"
          />
          <text
            x="622"
            y="82"
            textAnchor="middle"
            fill="#1A3C2B"
            fontSize="20"
          >
            🧑‍💻
          </text>
          <text
            x="622"
            y="101"
            textAnchor="middle"
            fill="#3A3A38"
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
            rx="2"
            fill="#ffffff"
            stroke="rgba(58,58,56,0.2)"
          />
          <text
            x="622"
            y="154"
            textAnchor="middle"
            fill="#1A3C2B"
            fontSize="20"
          >
            🤖
          </text>
          <text
            x="622"
            y="173"
            textAnchor="middle"
            fill="#3A3A38"
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
            fill="rgba(58,58,56,0.5)"
            letterSpacing="0.06em"
          >
            Rust + Python · Arrow IPC · pipe-native · agent-ready
          </text>
        </svg>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-3 gap-3 w-full max-w-[760px]">
        <FeatureCard
          icon="⚡"
          name="Fast"
          desc="Index 10K files in <1s. Rust core, zero-copy Arrow."
        />
        <FeatureCard
          icon="🔍"
          name="Universal"
          desc="PDFs, images, video, audio — one interface."
        />
        <FeatureCard
          icon="🔗"
          name="Composable"
          desc="Pipes to jq. DataFrames in Python. Built for agents."
        />
      </div>

      {/* Install — curl only */}
      <div className="font-mono text-[12px] text-[var(--text-muted)] flex flex-col items-center gap-1">
        <code className="bg-[var(--panel)] border border-[var(--border)] rounded-sm px-2 py-1 text-[var(--text-secondary)]">
          curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
        </code>
      </div>

      <GettingStarted />
    </div>
  );
}
