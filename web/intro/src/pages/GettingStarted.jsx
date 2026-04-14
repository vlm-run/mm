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

function Code({ children }) {
  return (
    <pre className="code-block">
      {children}
    </pre>
  );
}

function P({ children }) {
  return <p className="text-[13px] text-[var(--text-secondary)] mb-3">{children}</p>;
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

export default function GettingStarted() {
  return (
    <div className="animate-slide-up space-y-6">
      <div>
        <h1 className="text-[22px] font-bold text-[var(--text-primary)]">
          Getting Started
        </h1>
        <p className="text-[14px] text-[var(--text-secondary)] mt-1">
          Install mm, configure a VLM provider, and start working with
          multimodal files.
        </p>
      </div>

      {/* Installation */}
      <Section title="Installation">
        <P>Install mm via the pre-built wheels:</P>
        
        <P>macOS / Linux:</P>
        <Code>
          <span className="prompt">$ </span>
          curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
        </Code>

        <div className="my-5"></div>

        <P>Windows (PowerShell):</P>
        <Code>
          <span className="prompt">&gt; </span>
          irm https://vlm-run.github.io/mm/install/install.ps1 | iex
        </Code>
      </Section>

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
          profiles: <code className="font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1">ollama</code>,{" "}
          <code className="font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1">gemini</code>, and{" "}
          <code className="font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1">vlmrun</code>.
        </P>
        <Code>
          <span className="comment"># Use an existing reserved profile</span>
          {"\n"}
          <span className="prompt">$ </span>mm profile update ollama --base-url
          http://localhost:11434/v1 --model qwen3vl-8b{"\n\n"}
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
          <span className="prompt">$ </span>mm grep "photo of me and my dog in a
          park" ~/photos{"\n\n"}
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
          <span className="comment">
            # text summary + page count + embedded image count
          </span>
          {"\n"}
          <span className="prompt">$ </span>mm cat image.jpg
          {"    "}
          <span className="comment">
            # description + tags + EXIF metadata
          </span>
          {"\n"}
          <span className="prompt">$ </span>mm cat video.mp4
          {"    "}
          <span className="comment">
            # scene summary + transcript + keyframe grid
          </span>
        </Code>

        <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
          Batch operations
        </h3>
        <Code>
          <span className="prompt">$ </span>mm wc ~/docs
          {"              "}
          <span className="comment">
            # file count, bytes, lines, token estimate
          </span>
          {"\n"}
          <span className="prompt">$ </span>mm find ~/videos
          {"          "}
          <span className="comment">
            # list with tags, duration, resolution
          </span>
          {"\n"}
          <span className="prompt">$ </span>mm cat -m accurate video.mp4
          {"  "}
          <span className="comment">
            # full context: transcript + scenes
          </span>
        </Code>

        <h3 className="text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2">
          Agentic integration
        </h3>
        <P>Use mm directly as a tool or as a skill for coding assistants:</P>
        <ul className="list-disc list-inside text-[13px] text-[var(--text-secondary)] space-y-1 ml-1">
          <li>
            <em>
              "Find all invoices in ~/Downloads and create a markdown table with
              totals"
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

      {/* Benchmarks */}
      <Section title="Benchmarks">
        <P>Benchmark mm against native Unix commands with hyperfine:</P>
        <Code>
          <span className="prompt">$ </span>hyperfine --warmup 3 'grep -R TODO
          python' "mm grep 'TODO' python"
        </Code>
        <P>Or run the built-in benchmark suite:</P>
        <Code>
          <span className="prompt">$ </span>mm bench ~/data/mmbench-mini --format
          rich
        </Code>
      </Section>
    </div>
  );
}
