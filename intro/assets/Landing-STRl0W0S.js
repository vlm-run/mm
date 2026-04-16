import{r as c,j as e}from"./index-DoESUVX7.js";/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const N=(...s)=>s.filter((t,a,n)=>!!t&&t.trim()!==""&&n.indexOf(t)===a).join(" ").trim();/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=s=>s.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=s=>s.replace(/^([A-Z])|[\s-_]+(\w)/g,(t,a,n)=>n?n.toUpperCase():a.toLowerCase());/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const v=s=>{const t=S(s);return t.charAt(0).toUpperCase()+t.slice(1)};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var x={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=s=>{for(const t in s)if(t.startsWith("aria-")||t==="role"||t==="title")return!0;return!1},P=c.createContext({}),A=()=>c.useContext(P),z=c.forwardRef(({color:s,size:t,strokeWidth:a,absoluteStrokeWidth:n,className:m="",children:l,iconNode:b,...u},g)=>{const{size:d=24,strokeWidth:f=2,absoluteStrokeWidth:y=!1,color:w="currentColor",className:k=""}=A()??{},C=n??y?Number(a??f)*24/Number(t??d):a??f;return c.createElement("svg",{ref:g,...x,width:t??d??x.width,height:t??d??x.height,stroke:s??w,strokeWidth:C,className:N("lucide",k,m),...!l&&!I(u)&&{"aria-hidden":"true"},...u},[...b.map(([L,$])=>c.createElement(L,$)),...Array.isArray(l)?l:[l]])});/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const j=(s,t)=>{const a=c.forwardRef(({className:n,...m},l)=>c.createElement(z,{ref:l,iconNode:t,className:N(`lucide-${M(v(s))}`,`lucide-${s}`,n),...m}));return a.displayName=v(s),a};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const F=[["path",{d:"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",key:"1cjeqo"}],["path",{d:"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",key:"19qd67"}]],q=j("link",F);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const U=[["path",{d:"m21 21-4.34-4.34",key:"14j7rj"}],["circle",{cx:"11",cy:"11",r:"8",key:"4ej97u"}]],D=j("search",U);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const E=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],O=j("zap",E);function r({children:s}){return e.jsx("pre",{className:"code-block",children:s})}function i({children:s}){return e.jsx("p",{className:"text-[13px] text-[var(--text-secondary)] mb-3",children:s})}function o({title:s,children:t}){return e.jsxs("section",{className:"panel p-6 animate-slide-up",children:[e.jsx("h2",{className:"text-[16px] font-semibold text-[var(--text-primary)] mb-4",children:s}),t]})}function R({headers:s,rows:t}){return e.jsx("div",{className:"overflow-x-auto mb-3",children:e.jsxs("table",{children:[e.jsx("thead",{children:e.jsx("tr",{children:s.map(a=>e.jsx("th",{children:a},a))})}),e.jsx("tbody",{children:t.map((a,n)=>e.jsx("tr",{children:a.map((m,l)=>e.jsx("td",{className:"font-mono text-[13px]",children:m},l))},n))})]})})}function p({children:s}){return e.jsx("code",{className:"font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1",children:s})}function W(){return e.jsxs("div",{className:"w-full mt-16",children:[e.jsx("h1",{className:"text-2xl text-center font-bold text-[var(--text-primary)] mb-4",children:"Getting Started"}),e.jsxs("details",{className:"panel",children:[e.jsx("summary",{className:"px-6 py-4 cursor-pointer text-[14px] font-semibold text-[var(--text-primary)] select-none",children:"Installation (extended)"}),e.jsxs("div",{className:"px-6 pb-6 space-y-4",children:[e.jsxs("div",{children:[e.jsx(i,{children:e.jsx("strong",{children:"PyPI"})}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# pip"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"pip install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uv"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uv pip install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uv tool (global)"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uv tool install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uvx (direct use)"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uvx --from mm-ctx mm find --tree"]})]}),e.jsxs("div",{children:[e.jsx(i,{children:e.jsx("strong",{children:"Shell installer"})}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# macOS / Linux"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh",`

`,e.jsx("span",{className:"comment",children:"# Windows (PowerShell)"}),`
`,e.jsx("span",{className:"prompt",children:"> "}),"irm https://vlm-run.github.io/mm/install/install.ps1 | iex"]})]})]})]}),e.jsxs("div",{className:"w-full mt-6 space-y-6",children:[e.jsxs(o,{title:"VLM access",children:[e.jsx(i,{children:"mm requires access to a VLM on a live server for accurate-mode (LLM-powered) operations. Recommended models:"}),e.jsx(R,{headers:["Provider","Models"],rows:[["Qwen","qwen3vl-2b|4b|8b|32b, qwen3.5:0.8b|2b|9b|27b"],["Gemini","gemini-2.5-flash-lite, gemini-3.1-flash-lite-preview"]]})]}),e.jsxs(o,{title:"Profile setup",children:[e.jsxs(i,{children:["mm uses profiles to store provider credentials. There are 3 reserved profiles: ",e.jsx(p,{children:"ollama"}),","," ",e.jsx(p,{children:"gemini"}),", and"," ",e.jsx(p,{children:"vlmrun"}),"."]}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# Use an existing reserved profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile update ollama --base-url http://localhost:11434/v1 --model qwen3vl-8b",`

`,e.jsx("span",{className:"comment",children:"# Or create a custom profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile add fermi \\",`
`,"    ","--base-url https://openrouter.ai/api/v1 \\",`
`,"    ",'--api-key "your-openrouter-api-key" \\',`
`,"    ","--model google/gemini-2.5-flash-lite",`

`,e.jsx("span",{className:"comment",children:"# Set the active profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile use fermi"]})]}),e.jsxs(o,{title:"Integrations",children:[e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mb-2",children:"Claude Code"}),e.jsx(i,{children:"Install the mm-cli-skill via the skill marketplace:"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"claude",`
`,e.jsx("span",{className:"prompt",children:"> "}),"/plugin marketplace add vlm-run/skills",`
`,e.jsx("span",{className:"prompt",children:"> "}),"/plugin install mm-cli-skill@vlm-run/skills",`
`,e.jsx("span",{className:"prompt",children:"> "}),"Organize my ~/Downloads folder using mm"]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Universal assistants"}),e.jsx(i,{children:"Install mm-cli-skill globally so any CLI assistant or agentic tool can discover it:"}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# One-time setup"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"npx skills add vlm-run/skills@mm-cli-skill",`

`,e.jsx("span",{className:"comment",children:"# Then use any CLI assistant — it will discover mm automatically"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),'openclaw "Organize my ~/Downloads folder using mm"',`
`,e.jsx("span",{className:"prompt",children:"$ "}),'codex "Find all PDFs in ~/docs and summarize them with mm"']})]}),e.jsxs(o,{title:"Use cases",children:[e.jsxs(i,{children:["Use mm directly or through a CLI assistant (e.g."," ",e.jsx("code",{className:"font-mono text-[12px]",children:'claude "Organize ~/Downloads using mm"'}),")."]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mb-2",children:"Semantic search"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),'mm grep "photo of me and my dog in a park" ~/photos',`

`,e.jsx("span",{className:"output",children:"Returns matching images and videos (via keyframe analysis)."})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"File inspection & extraction"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm cat report.pdf","    ",e.jsx("span",{className:"comment",children:"# text extraction from PDF"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat image.jpg","    ",e.jsx("span",{className:"comment",children:"# dimensions + MIME + hash + EXIF"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat video.mp4","    ",e.jsx("span",{className:"comment",children:"# resolution + duration + codecs"})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Batch operations"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm wc ~/docs","              ",e.jsx("span",{className:"comment",children:"# file count, bytes, lines, tokens"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm find ~/videos","          ",e.jsx("span",{className:"comment",children:"# list files with kind, size, ext"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat video.mp4 -m accurate","  ",e.jsx("span",{className:"comment",children:"# mosaic + transcript → LLM description"})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Agentic integration"}),e.jsx(i,{children:"Use mm directly as a tool or as a skill for coding assistants:"}),e.jsxs("ul",{className:"list-disc list-inside text-[13px] text-[var(--text-secondary)] space-y-1 ml-1",children:[e.jsx("li",{children:e.jsx("em",{children:'"Find all invoices in ~/Downloads and create a markdown table with totals"'})}),e.jsx("li",{children:e.jsx("em",{children:'"Clip the first scene from video.mp4"'})}),e.jsx("li",{children:e.jsx("em",{children:'"Extract all faces from ~/events/wedding"'})})]})]}),e.jsx(o,{title:"Benchmark",children:e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm bench ~/data/mmbench-mini --format rich",`

`,e.jsx("span",{className:"output",children:`  #   Command                       Mean     ±Std  Speed   MB/s          bps
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
  L2  mm cat <video> --mode fast   41.29s    5.68s 6.12x    0.7    3.25 Gbps`})]})})]})]})}const B=`███╗   ███╗███╗   ███╗
████╗ ████║████╗ ████║
██╔████╔██║██╔████╔██║
██║╚██╔╝██║██║╚██╔╝██║
██║ ╚═╝ ██║██║ ╚═╝ ██║
╚═╝     ╚═╝╚═╝     ╚═╝`;function h({icon:s,name:t,desc:a}){return e.jsxs("div",{className:"panel p-4 text-center",children:[e.jsx("div",{className:"flex justify-center mb-1",children:s}),e.jsx("div",{className:"font-mono text-[10px] font-semibold uppercase tracking-[0.1em] mb-1",style:{color:"var(--forest)"},children:t}),e.jsx("div",{className:"text-[12px] text-[var(--text-secondary)] leading-relaxed",children:a})]})}function _(){return e.jsxs("div",{className:"animate-slide-up max-w-3xl mx-auto flex flex-col items-center gap-8",children:[e.jsxs("div",{className:"text-center",children:[e.jsx("pre",{className:"font-mono text-[clamp(0.5rem,1.5vw,1rem)] leading-tight font-bold whitespace-pre",style:{color:"var(--forest)"},children:B}),e.jsx("p",{className:"mt-3 text-[17px] tracking-wide",children:e.jsx("span",{className:"font-semibold",style:{fontFamily:"var(--font-heading)",color:"var(--forest)"},children:"Fast, multimodal file intelligence for agents."})}),e.jsx("p",{className:"mt-1.5 text-[13px] text-[var(--text-secondary)] tracking-wide font-mono",children:"find · cat · grep — rebuilt for the multimodal era."})]}),e.jsxs("div",{className:"grid grid-cols-3 gap-3 w-full mt-10 max-w-[760px]",children:[e.jsx(h,{icon:e.jsx(O,{size:20,color:"var(--forest)"}),name:"Fast",desc:"Index 10K files in <1s. Rust core, zero-copy Arrow."}),e.jsx(h,{icon:e.jsx(D,{size:20,color:"var(--forest)"}),name:"Universal",desc:"PDFs, images, video, audio — one interface."}),e.jsx(h,{icon:e.jsx(q,{size:20,color:"var(--forest)"}),name:"Composable",desc:"Pipes to jq. DataFrames in Python. Built for agents."})]}),e.jsxs("div",{className:"font-mono text-[12px] text-[var(--text-muted)] flex flex-col items-center gap-1.5",children:[e.jsx("code",{className:"bg-[var(--panel)] border border-[var(--border)] rounded-sm px-2 py-1 text-[var(--text-secondary)]",children:"pip install mm-ctx"}),e.jsx("span",{className:"text-[11px] tracking-wide",children:"Rust + Python · Arrow IPC · pipe-native · agent-ready"})]}),e.jsx(W,{})]})}export{_ as default};
