import { Zap, Search, Link } from "lucide-react";
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
      <div className="flex justify-center mb-1">{icon}</div>
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
            Fast, multimodal file intelligence for agents.
          </span>
        </p>
        <p className="mt-1.5 text-[13px] text-[var(--text-secondary)] tracking-wide font-mono">
          find · cat · grep — rebuilt for the multimodal era.
        </p>
      </div>

      {/* Concept Diagram */}
      {/* <div className="w-full max-w-[760px]">

      </div> */}

      {/* Feature cards */}
      <div className="grid grid-cols-3 gap-3 w-full mt-10 max-w-[760px]">
        <FeatureCard
          icon={<Zap size={20} color="var(--forest)" />}
          name="Fast"
          desc="Index 10K files in <1s. Rust core, zero-copy Arrow."
        />
        <FeatureCard
          icon={<Search size={20} color="var(--forest)" />}
          name="Universal"
          desc="PDFs, images, video, audio — one interface."
        />
        <FeatureCard
          icon={<Link size={20} color="var(--forest)" />}
          name="Composable"
          desc="Pipes to jq. DataFrames in Python. Built for agents."
        />
      </div>

      {/* Install — pip primary */}
      <div className="font-mono text-[12px] text-[var(--text-muted)] flex flex-col items-center gap-1.5">
        <code className="bg-[var(--panel)] border border-[var(--border)] rounded-sm px-2 py-1 text-[var(--text-secondary)]">
          pip install mm-ctx
        </code>
        <span className="text-[11px] tracking-wide">
          Rust + Python · Arrow IPC · pipe-native · agent-ready
        </span>
      </div>

      <GettingStarted />
    </div>
  );
}
