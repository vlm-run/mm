function Code({ children }) {
  return <pre className="code-block">{children}</pre>;
}

function P({ children }) {
  return (
    <p className="text-[13px] text-[var(--text-secondary)] mb-3">{children}</p>
  );
}

function Section({ title, children }) {
  return (
    <section className="panel p-6 animate-slide-up">
      <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Table({ headers, rows }) {
  return (
    <div className="overflow-x-auto mb-3">
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} className="font-mono text-[13px]">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InlineCode({ children }) {
  return (
    <code className="font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1">
      {children}
    </code>
  );
}

export default function GettingStarted() {
  return (
    <div className="w-full mt-20">
      <h1 className="text-2xl text-center font-bold text-[var(--text-primary)] mb-4">
        Getting Started
      </h1>
      <details className="panel">
        <summary className="px-6 py-4 cursor-pointer text-[14px] font-semibold text-[var(--text-primary)] select-none">
          Installation (extended)
        </summary>
        <div className="px-6 pb-6 space-y-4">
          <div>
            <P>
              <strong>PyPI</strong>
            </P>
            <Code>
              <span className="comment"># pip</span>
              {"\n"}
              <span className="prompt">$ </span>pip install mm-ctx{"\n\n"}
              <span className="comment"># uv</span>
              {"\n"}
              <span className="prompt">$ </span>uv pip install mm-ctx{"\n\n"}
              <span className="comment"># uv tool (global)</span>
              {"\n"}
              <span className="prompt">$ </span>uv tool install mm-ctx{"\n\n"}
              <span className="comment"># uvx (direct use)</span>
              {"\n"}
              <span className="prompt">$ </span>uvx mm-ctx find --tree
            </Code>
          </div>

          <div>
            <P>
              <strong>Shell installer</strong>
            </P>
            <Code>
              <span className="comment"># macOS / Linux</span>
              {"\n"}
              <span className="prompt">$ </span>curl -LsSf
              https://vlm-run.github.io/mm/install/install.sh | sh{"\n\n"}
              <span className="comment"># Windows (PowerShell)</span>
              {"\n"}
              <span className="prompt">&gt; </span>irm
              https://vlm-run.github.io/mm/install/install.ps1 | iex
            </Code>
          </div>
        </div>
      </details>

    <div className="w-full mt-6 space-y-6">
        {/* VLM Access */}
        <Section title="VLM access">
          <P>
            mm requires access to a VLM on a live server for accurate-mode
            (LLM-powered) operations. Recommended models:
          </P>
          <Table
            headers={["Provider", "Models"]}
            rows={[
              [
                "Qwen",
                "qwen3vl-2b|4b|8b|32b, qwen3.5:0.8b|2b|9b|27b",
              ],
              [
                "Gemini",
                "gemini-2.5-flash-lite, gemini-3.1-flash-lite-preview",
              ],
            ]}
          />
        </Section>

        {/* Profile setup */}
        <Section title="Profile setup">
          <P>
            mm uses profiles to store provider credentials. There are 3 reserved
            profiles: <InlineCode>ollama</InlineCode>,{" "}
            <InlineCode>gemini</InlineCode>, and{" "}
            <InlineCode>vlmrun</InlineCode>.
          </P>
          <Code>
            <span className="comment"># Use an existing reserved profile</span>
            {"\n"}
            <span className="prompt">$ </span>mm profile update ollama
            --base-url http://localhost:11434/v1 --model qwen3vl-8b{"\n\n"}
            <span className="comment"># Or create a custom profile</span>
            {"\n"}
            <span className="prompt">$ </span>mm profile add fermi \{"\n"}
            {"    "}--base-url https://openrouter.ai/api/v1 \{"\n"}
            {"    "}--api-key "your-openrouter-api-key" \{"\n"}
            {"    "}--model google/gemini-2.5-flash-lite{"\n\n"}
            <span className="comment"># Set the active profile</span>
            {"\n"}
            <span className="prompt">$ </span>mm profile use fermi
          </Code>
        </Section>

        {/* Integrations */}
        <Section title="Integrations">
          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mb-2">
            Claude Code
          </h3>
          <P>Install the mm-skill via the skill marketplace:</P>
          <Code>
            <span className="prompt">$ </span>claude{"\n"}
            <span className="prompt">&gt; </span>/plugin marketplace add
            vlm-run/skills{"\n"}
            <span className="prompt">&gt; </span>/plugin install
            mm-skill@vlm-run/skills{"\n"}
            <span className="prompt">&gt; </span>Organize my ~/Downloads folder
            using mm
          </Code>

          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
            Other CLI assistants
          </h3>
          <P>
            Install mm-skill globally so any CLI assistant or agentic tool can
            discover it:
          </P>
          <Code>
            <span className="comment"># One-time setup</span>
            {"\n"}
            <span className="prompt">$ </span>npx skill add vlm-run/mm-skill
            {"\n\n"}
            <span className="comment">
              # Then use any CLI assistant — it will discover mm automatically
            </span>
            {"\n"}
            <span className="prompt">$ </span>openclaw "Organize my ~/Downloads
            folder using mm"{"\n"}
            <span className="prompt">$ </span>codex "Find all PDFs in ~/docs and
            summarize them with mm"
          </Code>
        </Section>

        {/* Use cases */}
        <Section title="Use cases">
          <P>
            Use mm directly or through a CLI assistant (e.g.{" "}
            <code className="font-mono text-[12px]">
              claude "Organize ~/Downloads using mm"
            </code>
            ).
          </P>

          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mb-2">
            Semantic search
          </h3>
          <Code>
            <span className="prompt">$ </span>mm grep "photo of me and my dog in
            a park" ~/photos{"\n\n"}
            <span className="output">
              Returns matching images and videos (via keyframe analysis).
            </span>
          </Code>

          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
            File inspection & extraction
          </h3>
          <Code>
            <span className="prompt">$ </span>mm cat report.pdf
            {"    "}
            <span className="comment"># text extraction from PDF</span>
            {"\n"}
            <span className="prompt">$ </span>mm cat image.jpg
            {"    "}
            <span className="comment"># dimensions + MIME + hash + EXIF</span>
            {"\n"}
            <span className="prompt">$ </span>mm cat video.mp4
            {"    "}
            <span className="comment"># resolution + duration + codecs</span>
          </Code>

          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
            Batch operations
          </h3>
          <Code>
            <span className="prompt">$ </span>mm wc ~/docs
            {"              "}
            <span className="comment">
              # file count, bytes, lines, tokens
            </span>
            {"\n"}
            <span className="prompt">$ </span>mm find ~/videos
            {"          "}
            <span className="comment"># list files with kind, size, ext</span>
            {"\n"}
            <span className="prompt">$ </span>mm cat video.mp4 -m accurate
            {"  "}
            <span className="comment">
              # mosaic + transcript → LLM description
            </span>
          </Code>

          <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
            Agentic integration
          </h3>
          <P>Use mm directly as a tool or as a skill for coding assistants:</P>
          <ul className="list-disc list-inside text-[13px] text-[var(--text-secondary)] space-y-1 ml-1">
            <li>
              <em>
                "Find all invoices in ~/Downloads and create a markdown table
                with totals"
              </em>
            </li>
            <li>
              <em>"Clip the first scene from video.mp4"</em>
            </li>
            <li>
              <em>"Extract all faces from ~/events/wedding"</em>
            </li>
          </ul>
        </Section>

        {/* Benchmark */}
        <Section title="Benchmark">
          <Code>
            <span className="prompt">$ </span>mm bench ~/data/mmbench-mini --format rich{"\n\n"}
            <span className="output">{
`  #   Command                       Mean     ±Std  Speed   MB/s          bps
───── ──────────────────────────── ─────── ──────── ───── ─────── ───────────
  L0  mm find .                     344ms   0.35ms 11.6x  121.9    1.02 Gbps
  L0  mm wc .                       399ms   8.36ms 10.0x  105.3  883.43 Mbps
  L0  mm sql 'GROUP BY kind'        663ms   4.57ms 6.03x   63.3  531.34 Mbps
  L0  mm find --kind image          382ms   30.4ms 10.5x  109.9  922.26 Mbps
───── ──────────────────────────── ─────── ──────── ───── ─────── ───────────
  L1  mm cat <image>                7.37s    257ms 0.14x    0.0    1.00 Mbps
  L1  mm cat <video>               34.18s    1.39s 7.39x    0.8    3.92 Gbps
  L1  mm cat <pdf>                  4.15s    497ms 0.24x    0.1  672.78 kbps
  L1  mm grep /pattern/             660ms   7.57ms 6.06x   63.6  533.38 Mbps
───── ──────────────────────────── ─────── ──────── ───── ─────── ───────────
  L2  mm cat <image> --mode fast    7.29s    1.26s 0.14x    0.0    1.01 Mbps
  L2  mm cat <video> --mode fast   41.29s    5.68s 6.12x    0.7    3.25 Gbps`
            }</span>
          </Code>
        </Section>
      </div>
    </div>
  );
}
