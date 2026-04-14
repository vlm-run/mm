const DATASET = {
  path: "~/data/mmbench-tiny/",
  files: 9,
  size: "43.1 MB",
  contents: [
    "1-vqa-car.jpg",
    "BillDownload-8pg.pdf",
    "audio_health_check.wav",
    "bakery.mp4",
    "dogs.jpg",
    "fine-tuning-deck.pdf",
    "how_to_build_an_mvp.mp3",
    "invoice.jpg",
    "two_minute_rules.mp3",
  ],
};

const recipes = [
  {
    id: "wc",
    title: "Count files, size & tokens",
    desc: "Get a quick summary of what's in a directory — file counts, total size, estimated lines and tokens, broken down by kind.",
    examples: [
      {
        cmd: "mm wc ~/data/mmbench-tiny/",
        output: `kind      files  size      lines(est) tokens(est) tok_per_mb
audio     3      13.9 MB   0          255         18
document  2      702.3 KB  557        4.6K        6.7K
image     3      594.9 KB  0          3.0K        5.1K
video     1      28.0 MB   0          85          3
—————
total     9      43.1 MB   557        7.9K        183
48ms`,
      },
      {
        cmd: "mm wc ~/data/mmbench-tiny/ --kind document --format json",
        output: `{"files": 2, "size": 719156, "lines (est.)": 557, "tokens (est.)": 4578, "tok_per_mb": 6675}`,
      },
    ],
  },
  {
    id: "find",
    title: "Find & list files",
    desc: "Tabular listing, tree view, schema inspection, filtering by kind/size/name, and custom column selection.",
    examples: [
      {
        cmd: "mm find ~/data/mmbench-tiny/",
        output: `kind      size       path
image     39080      1-vqa-car.jpg
audio     14296087   how_to_build_an_mvp.mp3
document  348978     BillDownload-8pg.pdf
audio     29184      audio_health_check.wav
image     147391     invoice.jpg
document  370178     fine-tuning-deck.pdf
video     29346272   bakery.mp4
audio     242135     two_minute_rules.mp3
image     422683     dogs.jpg
8ms`,
      },
      {
        cmd: "mm find ~/data/mmbench-tiny/ --tree --depth 1",
        output: `/Users/sudeep/data/mmbench-tiny  (9 files, 43.1 MB)
├── 1-vqa-car.jpg            [38.2 KB]
├── BillDownload-8pg.pdf     [340.8 KB]
├── audio_health_check.wav   [28.5 KB]
├── bakery.mp4               [28.0 MB]
├── dogs.jpg                 [412.8 KB]
├── fine-tuning-deck.pdf     [361.5 KB]
├── how_to_build_an_mvp.mp3  [13.6 MB]
├── invoice.jpg              [143.9 KB]
└── two_minute_rules.mp3     [236.5 KB]
9ms`,
      },
      {
        cmd: "mm find ~/data/mmbench-tiny/ --kind image --columns name,kind,size,ext",
        output: `name           kind   size    ext
1-vqa-car.jpg  image  39080   .jpg
invoice.jpg    image  147391  .jpg
dogs.jpg       image  422683  .jpg`,
      },
      {
        cmd: "mm find ~/data/mmbench-tiny/ --min-size 1mb --sort size --reverse",
        output: `kind   size      path
video  29346272  bakery.mp4
audio  14296087  how_to_build_an_mvp.mp3`,
      },
      {
        cmd: 'mm find ~/data/mmbench-tiny/ --name "invoice"',
        output: `kind   size    path
image  147391  invoice.jpg`,
      },
    ],
  },
  {
    id: "find-schema",
    title: "Inspect schema",
    desc: "See all available columns, their Arrow types, and sample values. Useful before writing SQL queries.",
    examples: [
      {
        cmd: "mm find ~/data/mmbench-tiny/ --schema",
        output: `column     type            description
path       string          Relative path from scan root
name       string          File name with extension
stem       string          File name without extension
ext        string          File extension including dot
size       uint64          File size in bytes
modified   timestamp[us]   Last modification (UTC)
created    timestamp[us]   Creation (UTC)
mime       string          MIME type inferred from ext
kind       string          image|video|document|code|audio|data|config|text|other
is_binary  bool            True if binary
depth      uint16          Directory depth relative to scan root
parent     string          Parent directory name
width      uint32          Pixel width (images/videos)
height     uint32          Pixel height (images/videos)`,
      },
    ],
  },
  {
    id: "cat",
    title: "Extract content (cat)",
    desc: "Auto-detects file type and extracts content accordingly — VLM captions for images/video, text extraction for PDFs, transcription for audio.",
    examples: [
      {
        cmd: "mm cat ~/data/mmbench-tiny/1-vqa-car.jpg",
        comment: "Image → VLM caption",
        output: `"Vintage car parked in front of a yellow building.
 Tags: car, vintage, classic, automobile, architecture"
2.6s · 38.2 KB · 14.5 KB/s`,
      },
      {
        cmd: "mm cat ~/data/mmbench-tiny/bakery.mp4",
        comment: "Video → keyframe mosaic + VLM description",
        output: `"A scene depicting the interior and exterior of a bakery, showing bakers
 working with dough, arranging baked goods, and interacting with customers
 in a retail setting. tags: bakery, baking, shop, workers"
9.2s · 28.0 MB · 3.0 MB/s`,
      },
      {
        cmd: "mm cat ~/data/mmbench-tiny/BillDownload-8pg.pdf -n 20",
        comment: "PDF → text extraction (first 20 lines)",
        output: `BillDownload-8pg.pdf — pages 1-1 of 8:

--- Page 1 ---
Learn about your newly redesigned bill and get deeper insights about your
usage by visiting TECOaccount.com
To ensure prompt credit, please return stub portion of this bill with your payment.
Pay your bill online at TampaElectric.com
Account #: 311000060005
Due Date: October 18, 2024
Amount Due: $342,775.48
SEAWORLD PARKS & ENTERTAINMENT LLC
C/O BUSCH GARDENS
P.O. BOX 9158
TAMPA, FL 33674-9158
18ms · 340.8 KB · 19.0 MB/s`,
      },
      {
        cmd: "mm cat ~/data/mmbench-tiny/two_minute_rules.mp3",
        comment: "Audio → Whisper transcription",
        output: `Transcript of two_minute_rules.mp3 (lang=en, model=medium, 1702ms):

[0.0s - 1.0s] After reading tons of productivity books, I came across so
many rules. Like the two-year rule, the five-minute rule, the five-second
rule. No, not that five-second rule. The problem is...
2.3s · 236.5 KB · 101.2 KB/s`,
      },
    ],
  },
  {
    id: "grep",
    title: "Search across files",
    desc: "Full-text grep across extracted content, scoped by file kind.",
    examples: [
      {
        cmd: 'mm grep "TECO" ~/data/mmbench-tiny/ --kind document',
        output: `BillDownload-8pg.pdf:1:Learn about your newly redesigned bill ... TECOaccount.com
BillDownload-8pg.pdf:17:TECO
BillDownload-8pg.pdf:20:Make check payable to: TECO
BillDownload-8pg.pdf:90:Visit TECOaccount.com for
BillDownload-8pg.pdf:100:TECO
BillDownload-8pg.pdf:107:at TECOaccount.com.
172ms`,
      },
    ],
  },
  {
    id: "sql",
    title: "SQL queries",
    desc: "Run SQL against scanned file metadata. Supports ephemeral in-memory tables from directory scans, plus persistent L2 result and chunk tables.",
    examples: [
      {
        cmd: "mm sql --list-tables",
        output: `table       source         stored
files       scan + SQLite  ephemeral
l2_results  SQLite         empty
chunks      SQLite         empty`,
      },
    ],
  },
  {
    id: "profile",
    title: "Profile & config",
    desc: "Manage LLM provider profiles and extraction settings.",
    examples: [
      {
        cmd: "mm profile list",
        output: `profile  active  base_url                       model
gemini           https://openrouter.ai/api/v1   google/gemini-2.5-flash-lite
ollama   ✓       http://localhost:11434         gemma4:e2b
vlmrun           https://mm-ctx.ngrok.io/v1     Qwen/Qwen3.5-0.8B`,
      },
      {
        cmd: "mm config show",
        output: `key                            value
mode.fast.whisper_model        tiny
mode.fast.audio_speed          2.0
mode.accurate.whisper_model    medium
mode.accurate.audio_speed      1.0`,
      },
    ],
  },
];

function CodeBlock({ cmd, output, comment }) {
  return (
    <div className="mb-3">
      <pre className="code-block">
        {comment && (
          <>
            <span className="comment"># {comment}</span>
            {"\n"}
          </>
        )}
        <span className="prompt">$ </span>
        {cmd}
        {output && (
          <>
            {"\n\n"}
            <span className="output">{output}</span>
          </>
        )}
      </pre>
    </div>
  );
}

function RecipeSection({ recipe }) {
  return (
    <section id={recipe.id} className="panel p-6 animate-slide-up">
      <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-1">
        {recipe.title}
      </h2>
      <p className="text-[13px] text-[var(--text-secondary)] mb-4">
        {recipe.desc}
      </p>
      {recipe.examples.map((ex, i) => (
        <CodeBlock key={i} cmd={ex.cmd} output={ex.output} comment={ex.comment} />
      ))}
    </section>
  );
}

export default function Cookbook() {
  return (
    <div className="animate-slide-up space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-[var(--text-primary)]">
          Cookbook
        </h1>
        <p className="text-[14px] text-[var(--text-secondary)] mt-1">
          Hands-on recipes using a 9-file, 43 MB multimodal dataset — images,
          PDFs, video, and audio.
        </p>
      </div>

      {/* Dataset overview */}
      <div className="panel p-5">
        <div className="flex items-center gap-3 mb-3">
          <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[var(--forest)]">
            Dataset
          </span>
          <code className="font-mono text-[12px] text-[var(--text-secondary)] bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-0.5">
            {DATASET.path}
          </code>
          <span className="font-mono text-[11px] text-[var(--text-muted)]">
            {DATASET.files} files · {DATASET.size}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {DATASET.contents.map((f) => {
            const ext = f.split(".").pop();
            const kindColor =
              {
                jpg: "#FF8C69",
                pdf: "#F4D35E",
                mp4: "#1A3C2B",
                mp3: "#9EFFBF",
                wav: "#9EFFBF",
              }[ext] || "var(--text-muted)";
            return (
              <span
                key={f}
                className="font-mono text-[11px] border rounded px-2 py-0.5"
                style={{
                  borderColor: kindColor + "40",
                  color: kindColor,
                  background: kindColor + "08",
                }}
              >
                {f}
              </span>
            );
          })}
        </div>
      </div>

      {/* TOC */}
      <div className="panel p-4">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] block mb-2">
          Recipes
        </span>
        <div className="flex flex-wrap gap-1.5">
          {recipes.map((r) => (
            <a
              key={r.id}
              href={`#${r.id}`}
              className="font-mono text-[11px] text-[var(--forest)] border border-[var(--border)] rounded px-2 py-0.5 hover:border-[var(--forest)] transition-colors no-underline"
            >
              {r.title}
            </a>
          ))}
        </div>
      </div>

      {/* Recipe sections */}
      {recipes.map((r) => (
        <RecipeSection key={r.id} recipe={r} />
      ))}
    </div>
  );
}
