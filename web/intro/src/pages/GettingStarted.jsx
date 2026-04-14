function Code({ children }) {
  return <pre className="code-block">{children}</pre>;
}

function P({ children }) {
  return (
    <p className="text-[13px] text-[var(--text-secondary)] mb-3">{children}</p>
  );
}

export default function GettingStarted() {
  return (
    <div className="w-full max-w-[760px] mt-20">
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
              <strong>Global installs</strong>
            </P>
            <Code>
              <span className="comment"># Shell installer</span>
              {"\n"}
              <span className="prompt">$ </span>curl -LsSf
              https://vlm-run.github.io/mm/install/install.sh | sh{"\n\n"}
              <span className="comment"># Via uv tool</span>
              {"\n"}
              <span className="prompt">$ </span>uv tool install mm --index-url
              https://vlm-run.github.io/mm/install/simple/
            </Code>
          </div>

          <div>
            <P>
              <strong>Project installs</strong>
            </P>
            <Code>
              <span className="comment"># With uv</span>
              {"\n"}
              <span className="prompt">$ </span>uv pip install --index-url
              https://vlm-run.github.io/mm/install/simple/ mm{"\n\n"}
              <span className="comment"># Without uv</span>
              {"\n"}
              <span className="prompt">$ </span>pip install --index-url
              https://vlm-run.github.io/mm/install/simple/ mm
            </Code>
          </div>

          <div>
            <P>
              <strong>Direct use with uvx</strong>
            </P>
            <Code>
              <span className="prompt">$ </span>uvx --index-url
              https://vlm-run.github.io/mm/install/simple/ mm find --tree
            </Code>
          </div>

          <div>
            <P>
              <strong>Windows (PowerShell)</strong>
            </P>
            <Code>
              <span className="prompt">&gt; </span>irm
              https://vlm-run.github.io/mm/install/install.ps1 | iex
            </Code>
          </div>
        </div>
      </details>
    </div>
  );
}
