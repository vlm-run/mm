import{r as c,j as e}from"./index-Da29PAw0.js";/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=(...s)=>s.filter((t,n,a)=>!!t&&t.trim()!==""&&a.indexOf(t)===n).join(" ").trim();/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const L=s=>s.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=s=>s.replace(/^([A-Z])|[\s-_]+(\w)/g,(t,n,a)=>a?a.toUpperCase():n.toLowerCase());/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const y=s=>{const t=M(s);return t.charAt(0).toUpperCase()+t.slice(1)};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var h={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const $=s=>{for(const t in s)if(t.startsWith("aria-")||t==="role"||t==="title")return!0;return!1},z=c.createContext({}),F=()=>c.useContext(z),B=c.forwardRef(({color:s,size:t,strokeWidth:n,absoluteStrokeWidth:a,className:m="",children:l,iconNode:v,...j},b)=>{const{size:x=24,strokeWidth:u=2,absoluteStrokeWidth:N=!1,color:k="currentColor",className:w=""}=F()??{},C=a??N?Number(n??u)*24/Number(t??x):n??u;return c.createElement("svg",{ref:b,...h,width:t??x??h.width,height:t??x??h.height,stroke:s??k,strokeWidth:C,className:g("lucide",w,m),...!l&&!$(j)&&{"aria-hidden":"true"},...j},[...v.map(([A,S])=>c.createElement(A,S)),...Array.isArray(l)?l:[l]])});/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const i=(s,t)=>{const n=c.forwardRef(({className:a,...m},l)=>c.createElement(B,{ref:l,iconNode:t,className:g(`lucide-${L(y(s))}`,`lucide-${s}`,a),...m}));return n.displayName=y(s),n};/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=[["path",{d:"M12 8V4H8",key:"hb8ula"}],["rect",{width:"16",height:"12",x:"4",y:"8",rx:"2",key:"enze0r"}],["path",{d:"M2 14h2",key:"vft8re"}],["path",{d:"M20 14h2",key:"4cs60a"}],["path",{d:"M15 13v2",key:"1xurst"}],["path",{d:"M9 13v2",key:"rq6x2g"}]],_=i("bot",I);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const W=[["path",{d:"M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z",key:"1oefj6"}],["path",{d:"M14 2v5a1 1 0 0 0 1 1h5",key:"wfsgrz"}],["path",{d:"M10 9H8",key:"b1mrlr"}],["path",{d:"M16 13H8",key:"t4e002"}],["path",{d:"M16 17H8",key:"z1uh3a"}]],P=i("file-text",W);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2",ry:"2",key:"1m3agn"}],["circle",{cx:"9",cy:"9",r:"2",key:"af1f0g"}],["path",{d:"m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21",key:"1xmnt7"}]],q=i("image",O);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const E=[["path",{d:"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",key:"1cjeqo"}],["path",{d:"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",key:"19qd67"}]],U=i("link",E);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["path",{d:"M9 18V5l12-2v13",key:"1jmyc2"}],["circle",{cx:"6",cy:"18",r:"3",key:"fqmcym"}],["circle",{cx:"18",cy:"16",r:"3",key:"1hluhg"}]],R=i("music",D);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=[["path",{d:"m21 21-4.34-4.34",key:"14j7rj"}],["circle",{cx:"11",cy:"11",r:"8",key:"4ej97u"}]],G=i("search",V);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M12 4v16",key:"1654pz"}],["path",{d:"M4 7V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2",key:"e0r10z"}],["path",{d:"M9 20h6",key:"s66wpe"}]],H=i("type",T);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Z=[["path",{d:"m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5",key:"ftymec"}],["rect",{x:"2",y:"6",width:"14",height:"12",rx:"2",key:"158x01"}]],K=i("video",Z);/**
 * @license lucide-react v1.8.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const X=[["path",{d:"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",key:"1xq2db"}]],Y=i("zap",X);function r({children:s}){return e.jsx("pre",{className:"code-block",children:s})}function o({children:s}){return e.jsx("p",{className:"text-[13px] text-[var(--text-secondary)] mb-3",children:s})}function d({title:s,children:t}){return e.jsxs("section",{className:"panel p-6 animate-slide-up",children:[e.jsx("h2",{className:"text-[16px] font-semibold text-[var(--text-primary)] mb-4",children:s}),t]})}function Q({headers:s,rows:t}){return e.jsx("div",{className:"overflow-x-auto mb-3",children:e.jsxs("table",{children:[e.jsx("thead",{children:e.jsx("tr",{children:s.map(n=>e.jsx("th",{children:n},n))})}),e.jsx("tbody",{children:t.map((n,a)=>e.jsx("tr",{children:n.map((m,l)=>e.jsx("td",{className:"font-mono text-[13px]",children:m},l))},a))})]})})}function p({children:s}){return e.jsx("code",{className:"font-mono text-[12px] text-[var(--forest)] bg-[rgba(158,255,191,0.2)] rounded px-1",children:s})}function J(){return e.jsxs("div",{className:"w-full mt-20",children:[e.jsx("h1",{className:"text-2xl text-center font-bold text-[var(--text-primary)] mb-4",children:"Getting Started"}),e.jsxs("details",{className:"panel",children:[e.jsx("summary",{className:"px-6 py-4 cursor-pointer text-[14px] font-semibold text-[var(--text-primary)] select-none",children:"Installation (extended)"}),e.jsxs("div",{className:"px-6 pb-6 space-y-4",children:[e.jsxs("div",{children:[e.jsx(o,{children:e.jsx("strong",{children:"PyPI"})}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# pip"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"pip install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uv"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uv pip install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uv tool (global)"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uv tool install mm-ctx",`

`,e.jsx("span",{className:"comment",children:"# uvx (direct use)"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"uvx --from mm-ctx mm find --tree"]})]}),e.jsxs("div",{children:[e.jsx(o,{children:e.jsx("strong",{children:"Shell installer"})}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# macOS / Linux"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh",`

`,e.jsx("span",{className:"comment",children:"# Windows (PowerShell)"}),`
`,e.jsx("span",{className:"prompt",children:"> "}),"irm https://vlm-run.github.io/mm/install/install.ps1 | iex"]})]})]})]}),e.jsxs("div",{className:"w-full mt-6 space-y-6",children:[e.jsxs(d,{title:"VLM access",children:[e.jsx(o,{children:"mm requires access to a VLM on a live server for accurate-mode (LLM-powered) operations. Recommended models:"}),e.jsx(Q,{headers:["Provider","Models"],rows:[["Qwen","qwen3vl-2b|4b|8b|32b, qwen3.5:0.8b|2b|9b|27b"],["Gemini","gemini-2.5-flash-lite, gemini-3.1-flash-lite-preview"]]})]}),e.jsxs(d,{title:"Profile setup",children:[e.jsxs(o,{children:["mm uses profiles to store provider credentials. There are 3 reserved profiles: ",e.jsx(p,{children:"ollama"}),","," ",e.jsx(p,{children:"gemini"}),", and"," ",e.jsx(p,{children:"vlmrun"}),"."]}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# Use an existing reserved profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile update ollama --base-url http://localhost:11434/v1 --model qwen3vl-8b",`

`,e.jsx("span",{className:"comment",children:"# Or create a custom profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile add fermi \\",`
`,"    ","--base-url https://openrouter.ai/api/v1 \\",`
`,"    ",'--api-key "your-openrouter-api-key" \\',`
`,"    ","--model google/gemini-2.5-flash-lite",`

`,e.jsx("span",{className:"comment",children:"# Set the active profile"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm profile use fermi"]})]}),e.jsxs(d,{title:"Integrations",children:[e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mb-2",children:"Claude Code"}),e.jsx(o,{children:"Install the mm-cli-skill via the skill marketplace:"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"claude",`
`,e.jsx("span",{className:"prompt",children:"> "}),"/plugin marketplace add vlm-run/skills",`
`,e.jsx("span",{className:"prompt",children:"> "}),"/plugin install mm-cli-skill@vlm-run/skills",`
`,e.jsx("span",{className:"prompt",children:"> "}),"Organize my ~/Downloads folder using mm"]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Universal assistants"}),e.jsx(o,{children:"Install mm-cli-skill globally so any CLI assistant or agentic tool can discover it:"}),e.jsxs(r,{children:[e.jsx("span",{className:"comment",children:"# One-time setup"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"npx skills add vlm-run/skills@mm-cli-skill",`

`,e.jsx("span",{className:"comment",children:"# Then use any CLI assistant — it will discover mm automatically"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),'openclaw "Organize my ~/Downloads folder using mm"',`
`,e.jsx("span",{className:"prompt",children:"$ "}),'codex "Find all PDFs in ~/docs and summarize them with mm"']})]}),e.jsxs(d,{title:"Use cases",children:[e.jsxs(o,{children:["Use mm directly or through a CLI assistant (e.g."," ",e.jsx("code",{className:"font-mono text-[12px]",children:'claude "Organize ~/Downloads using mm"'}),")."]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mb-2",children:"Semantic search"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),'mm grep "photo of me and my dog in a park" ~/photos',`

`,e.jsx("span",{className:"output",children:"Returns matching images and videos (via keyframe analysis)."})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"File inspection & extraction"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm cat report.pdf","    ",e.jsx("span",{className:"comment",children:"# text extraction from PDF"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat image.jpg","    ",e.jsx("span",{className:"comment",children:"# dimensions + MIME + hash + EXIF"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat video.mp4","    ",e.jsx("span",{className:"comment",children:"# resolution + duration + codecs"})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Batch operations"}),e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm wc ~/docs","              ",e.jsx("span",{className:"comment",children:"# file count, bytes, lines, tokens"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm find ~/videos","          ",e.jsx("span",{className:"comment",children:"# list files with kind, size, ext"}),`
`,e.jsx("span",{className:"prompt",children:"$ "}),"mm cat video.mp4 -m accurate","  ",e.jsx("span",{className:"comment",children:"# mosaic + transcript → LLM description"})]}),e.jsx("h3",{className:"text-[14px] font-semibold text-[var(--text-primary)] mt-5 mb-2",children:"Agentic integration"}),e.jsx(o,{children:"Use mm directly as a tool or as a skill for coding assistants:"}),e.jsxs("ul",{className:"list-disc list-inside text-[13px] text-[var(--text-secondary)] space-y-1 ml-1",children:[e.jsx("li",{children:e.jsx("em",{children:'"Find all invoices in ~/Downloads and create a markdown table with totals"'})}),e.jsx("li",{children:e.jsx("em",{children:'"Clip the first scene from video.mp4"'})}),e.jsx("li",{children:e.jsx("em",{children:'"Extract all faces from ~/events/wedding"'})})]})]}),e.jsx(d,{title:"Benchmark",children:e.jsxs(r,{children:[e.jsx("span",{className:"prompt",children:"$ "}),"mm bench ~/data/mmbench-mini --format rich",`

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
  L2  mm cat <video> --mode fast   41.29s    5.68s 6.12x    0.7    3.25 Gbps`})]})})]})]})}const ee=`███╗   ███╗███╗   ███╗
████╗ ████║████╗ ████║
██╔████╔██║██╔████╔██║
██║╚██╔╝██║██║╚██╔╝██║
██║ ╚═╝ ██║██║ ╚═╝ ██║
╚═╝     ╚═╝╚═╝     ╚═╝`;function f({icon:s,name:t,desc:n}){return e.jsxs("div",{className:"panel p-4 text-center",children:[e.jsx("div",{className:"flex justify-center mb-1",children:s}),e.jsx("div",{className:"font-mono text-[10px] font-semibold uppercase tracking-[0.1em] mb-1",style:{color:"var(--forest)"},children:t}),e.jsx("div",{className:"text-[12px] text-[var(--text-secondary)] leading-relaxed",children:n})]})}function te(){return e.jsxs("div",{className:"animate-slide-up max-w-3xl mx-auto flex flex-col items-center gap-8",children:[e.jsxs("div",{className:"text-center",children:[e.jsx("pre",{className:"font-mono text-[clamp(0.5rem,1.5vw,1rem)] leading-tight font-bold whitespace-pre",style:{color:"var(--forest)"},children:ee}),e.jsx("p",{className:"mt-3 text-[17px] tracking-wide",children:e.jsx("span",{className:"font-semibold",style:{fontFamily:"var(--font-heading)",color:"var(--forest)"},children:"Fast, multimodal file intelligence for agents."})}),e.jsx("p",{className:"mt-1.5 text-[13px] text-[var(--text-secondary)] tracking-wide font-mono",children:"find · cat · grep — rebuilt for the multimodal era."})]}),e.jsx("div",{className:"w-full max-w-[760px]",children:e.jsxs("svg",{viewBox:"0 0 700 250",xmlns:"http://www.w3.org/2000/svg",fill:"none",className:"w-full h-auto",children:[e.jsx("defs",{children:e.jsx("marker",{id:"arrow",viewBox:"0 0 10 7",refX:"10",refY:"3.5",markerWidth:"8",markerHeight:"6",orient:"auto-start-reverse",children:e.jsx("path",{d:"M0,0 L10,3.5 L0,7",fill:"#1A3C2B",opacity:"0.5"})})}),e.jsx("rect",{x:"0",y:"10",width:"700",height:"220",rx:"2",fill:"rgba(26,60,43,0.03)"}),e.jsx("rect",{x:"18",y:"40",width:"120",height:"160",rx:"2",fill:"#ffffff",stroke:"rgba(58,58,56,0.2)"}),e.jsx("text",{x:"78",y:"60",textAnchor:"middle",fill:"#1A3C2B",fontSize:"10",fontWeight:"600",fontFamily:"var(--font-mono)",letterSpacing:"0.1em",children:"SOURCES"}),e.jsx("line",{x1:"30",y1:"68",x2:"126",y2:"68",stroke:"rgba(58,58,56,0.2)"}),[[88,P,"PDF"],[108,q,"Image"],[128,K,"Video"],[148,R,"Audio"],[168,H,"Text"]].map(([s,t,n])=>e.jsxs("g",{children:[e.jsx("foreignObject",{x:"30",y:s-11,width:"14",height:"14",children:e.jsx("div",{xmlns:"http://www.w3.org/1999/xhtml",style:{display:"flex",alignItems:"center",justifyContent:"center",width:14,height:14},children:e.jsx(t,{size:12,color:"#1A3C2B",strokeWidth:2})})}),e.jsx("text",{x:"50",y:s,fill:"#3A3A38",fontSize:"10",fontFamily:"var(--font-mono)",dominantBaseline:"auto",children:n})]},n)),e.jsx("text",{x:"34",y:"188",fill:"rgba(58,58,56,0.5)",fontSize:"9",fontFamily:"var(--font-mono)",children:"…"}),e.jsx("text",{x:"46",y:"188",fill:"rgba(58,58,56,0.5)",fontSize:"9",fontFamily:"var(--font-mono)",children:"and more"}),e.jsx("line",{x1:"143",y1:"120",x2:"182",y2:"120",stroke:"#1A3C2B",strokeOpacity:"0.4",strokeWidth:"1.5",markerEnd:"url(#arrow)"}),e.jsx("rect",{x:"188",y:"22",width:"320",height:"196",rx:"2",fill:"#ffffff",stroke:"#1A3C2B",strokeWidth:"1"}),e.jsx("text",{x:"348",y:"44",textAnchor:"middle",fill:"#1A3C2B",fontSize:"13",fontWeight:"700",fontFamily:"var(--font-mono)",letterSpacing:"0.12em",children:"mm"}),e.jsx("line",{x1:"202",y1:"52",x2:"494",y2:"52",stroke:"rgba(58,58,56,0.2)"}),e.jsx("rect",{x:"204",y:"66",width:"290",height:"60",rx:"2",fill:"#F7F7F5",stroke:"rgba(58,58,56,0.2)"}),e.jsx("text",{x:"218",y:"90",fill:"#1A3C2B",fontSize:"10",fontWeight:"600",fontFamily:"var(--font-mono)",children:"Context"}),e.jsx("text",{x:"218",y:"108",fill:"rgba(58,58,56,0.5)",fontSize:"8.5",fontFamily:"var(--font-mono)",children:"hash · kind · text · pages · duration · dimensions"}),e.jsx("rect",{x:"204",y:"142",width:"290",height:"60",rx:"2",fill:"#F7F7F5",stroke:"rgba(58,58,56,0.2)"}),e.jsx("text",{x:"218",y:"166",fill:"#1A3C2B",fontSize:"10",fontWeight:"600",fontFamily:"var(--font-mono)",children:"Semantic"}),e.jsx("text",{x:"218",y:"184",fill:"rgba(58,58,56,0.5)",fontSize:"8.5",fontFamily:"var(--font-mono)",children:"captions · embeddings · search · encoders · pipelines"}),e.jsx("line",{x1:"513",y1:"120",x2:"560",y2:"120",stroke:"#1A3C2B",strokeOpacity:"0.4",strokeWidth:"1.5",markerEnd:"url(#arrow)"}),e.jsx("rect",{x:"565",y:"93",width:"115",height:"54",rx:"2",fill:"#ffffff",stroke:"rgba(58,58,56,0.2)"}),e.jsx("foreignObject",{x:"610",y:"100",width:"24",height:"24",children:e.jsx("div",{xmlns:"http://www.w3.org/1999/xhtml",style:{display:"flex",alignItems:"center",justifyContent:"center",width:24,height:24},children:e.jsx(_,{size:18,color:"#1A3C2B",strokeWidth:2})})}),e.jsx("text",{x:"622",y:"137",textAnchor:"middle",fill:"#3A3A38",fontSize:"9",fontFamily:"var(--font-mono)",children:"Agents"}),e.jsx("text",{x:"350",y:"242",textAnchor:"middle",fontFamily:"var(--font-mono)",fontSize:"9",fill:"rgba(58,58,56,0.5)",letterSpacing:"0.06em",children:"Rust + Python · Arrow IPC · pipe-native · agent-ready"})]})}),e.jsxs("div",{className:"grid grid-cols-3 gap-3 w-full max-w-[760px]",children:[e.jsx(f,{icon:e.jsx(Y,{size:20,color:"var(--forest)"}),name:"Fast",desc:"Index 10K files in <1s. Rust core, zero-copy Arrow."}),e.jsx(f,{icon:e.jsx(G,{size:20,color:"var(--forest)"}),name:"Universal",desc:"PDFs, images, video, audio — one interface."}),e.jsx(f,{icon:e.jsx(U,{size:20,color:"var(--forest)"}),name:"Composable",desc:"Pipes to jq. DataFrames in Python. Built for agents."})]}),e.jsx("div",{className:"font-mono text-[12px] text-[var(--text-muted)] flex flex-col items-center gap-1",children:e.jsx("code",{className:"bg-[var(--panel)] border border-[var(--border)] rounded-sm px-2 py-1 text-[var(--text-secondary)]",children:"pip install mm-ctx"})}),e.jsx(J,{})]})}export{te as default};
