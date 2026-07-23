<script>
  import { onMount } from "svelte";
  import { slide } from "svelte/transition";
  import Chart from "../components/Chart.svelte";
  import ArtifactView from "../components/ArtifactView.svelte";
  import {
    fetchCell,
    fetchSession,
    fetchTranscript,
    fetchCaseSpec,
    fetchArtifacts,
    artifactUrl,
  } from "../api.js";

  let { assistant, profile, open = "" } = $props();
  let d = $state(null);
  let detail = $state({});
  const requested = new Set();
  const openSet = $derived(
    new Set(open ? open.split(",").filter(Boolean) : []),
  );
  onMount(async () => {
    d = await fetchCell(assistant, profile);
  });

  // URL is the source of truth: load each open session's cases once.
  $effect(() => {
    for (const sid of openSet) {
      if (!requested.has(sid)) {
        requested.add(sid);
        detail[sid] = { loading: true };
        fetchSession(sid).then((sd) => {
          detail[sid] = sd;
        });
      }
    }
  });

  function toggle(sid) {
    const next = new Set(openSet);
    next.has(sid) ? next.delete(sid) : next.add(sid);
    const qs = next.size ? `?open=${[...next].join(",")}` : "";
    window.location.hash = `#/cell/${encodeURIComponent(assistant)}/${encodeURIComponent(profile)}${qs}`;
  }

  const num = (v, s = "") => (v == null ? "–" : v + s);
  const fmtTokens = (v) =>
    v == null
      ? "–"
      : v >= 1e6
        ? (v / 1e6).toFixed(1) + "M"
        : v >= 1e3
          ? (v / 1e3).toFixed(1) + "k"
          : String(v);
  const ax = { ticks: { color: "#94a3b8" }, grid: { color: "#1e293b" } };
  const BRIGHT = "text-slate-100";
  const DIM = "text-slate-500";
  const tokClass = (w, wo) =>
    w == null && wo == null
      ? [DIM, DIM]
      : w == null
        ? [DIM, BRIGHT]
        : wo == null
          ? [BRIGHT, DIM]
          : w <= wo
            ? [BRIGHT, DIM]
            : [DIM, BRIGHT];

  const perCase = $derived.by(() => {
    if (!d?.cases) return { labels: [], datasets: [] };
    return {
      labels: d.cases.map((c) => c.case_id),
      datasets: [
        {
          label: "Without mm",
          data: d.cases.map((c) => c.without_mm),
          backgroundColor: "#52617a",
        },
        {
          label: "With mm",
          data: d.cases.map((c) => c.with_mm),
          backgroundColor: "#7e9bbf",
        },
      ],
    };
  });
  const perCaseOpts = {
    indexAxis: "y",
    scales: { x: { ...ax, beginAtZero: true, max: 100 }, y: ax },
    plugins: { legend: { labels: { color: "#cbd5e1" } } },
  };
  const perCaseH = $derived(Math.max(260, (d?.cases?.length ?? 0) * 30));
  const short = (id) => id.slice(0, 8);

  let txDialog = $state(null);
  let tx = $state(null);
  let txSession = $state("");
  let txCase = $state("");
  let txArm = $state("with_mm");
  let txTab = $state("transcript");
  let txLoading = $state(false);
  let spec = $state(null);
  let arts = $state([]);
  let artsLoading = $state(false);

  async function openTx(sid, cid) {
    txSession = sid;
    txCase = cid;
    txArm = "with_mm";
    txTab = "transcript";
    tx = null;
    spec = null;
    arts = [];
    txLoading = true;
    txDialog.showModal();
    const [data, sp] = await Promise.all([
      fetchTranscript(sid, cid),
      fetchCaseSpec(cid),
    ]);
    if (!data.with_mm && data.without_mm) txArm = "without_mm";
    tx = data;
    spec = sp;
    txLoading = false;
    loadArtifacts();
  }

  function setArm(k) {
    txArm = k;
    loadArtifacts();
  }

  async function loadArtifacts() {
    artsLoading = true;
    arts = await fetchArtifacts(txSession, txCase, txArm);
    artsLoading = false;
  }

  const specRest = $derived.by(() => {
    if (!spec) return "";
    const { prompt, ...rest } = spec;
    return JSON.stringify(rest, null, 2);
  });

  function parseLog(s) {
    return (s && s.trim() ? s.trim().split("\n") : []).map((line) => {
      const p = line.split("\t"); // <exit_code>\t<duration_s>\t<args>
      return { code: p[0], dur: p[1], args: p.slice(2).join("\t") };
    });
  }
  const logEntries = $derived(parseLog(tx?.[txArm]?.mm_log));
</script>

<a href="#/" class="text-sm text-slate-400 hover:text-blue-400 no-underline"
  >&larr; leaderboard</a
>
{#if d}
  <h1 class="text-2xl font-bold mt-2">
    {d.assistant} <span class="text-slate-500">/</span>
    {d.profile}
  </h1>
  <div class="text-xs text-slate-500 font-mono mt-1">{d.model || ""}</div>
  <div class="text-xs text-slate-600 font-mono break-all">
    {d.base_url || ""}
  </div>

  <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mt-5">
    {#each [["Without mm", d.overall.without_mm.correctness, ""], ["With mm", d.overall.with_mm.correctness, ""], ["Lift", d.overall.lift, ""], ["Speedup", d.overall.speedup, "×"]] as [label, val, suf]}
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div class="text-xs uppercase tracking-widest text-slate-400">
          {label}
        </div>
        <div class="text-2xl font-semibold mt-1 font-mono">
          {num(val, suf)}
        </div>
      </div>
    {/each}
    <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div class="text-xs uppercase tracking-widest text-slate-400">
        Tokens (wo/w)
      </div>
      <div class="text-xl font-semibold mt-1 font-mono">
        <span class={tokClass(d.overall.without_mm.token_sum, d.overall.with_mm.token_sum)[0]}>{fmtTokens(d.overall.without_mm.token_sum)}</span><span class={tokClass(d.overall.without_mm.token_sum, d.overall.with_mm.token_sum)[1]}> / {fmtTokens(d.overall.with_mm.token_sum)}</span>
      </div>
    </div>
  </div>

  <section class="mt-6">
    <h2
      class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2"
    >
      Sessions ({d.sessions.length})
    </h2>
    <div class="overflow-x-auto rounded-xl border border-slate-800">
      <table class="w-full text-sm">
        <thead class="bg-slate-900 text-slate-400"
          ><tr>
            <th class="text-left p-3">Session</th><th class="text-left p-3"
              >Started</th
            >
            <th class="text-right p-3">Runs</th><th class="text-right p-3"
              >Without %</th
            >
            <th class="text-right p-3">With %</th><th class="text-right p-3"
              >Lift</th
            ><th class="text-right p-3">Toks (wo/w)</th>
          </tr></thead
        >
        <tbody>
          {#each d.sessions as s (s.session_id)}
            <tr
              class="border-t border-slate-800 hover:bg-slate-800/60 cursor-pointer"
              onclick={() => toggle(s.session_id)}
            >
              <td class="p-3 text-blue-400 font-mono">
                <span class="inline-flex items-center gap-2">
                  <span
                    class="text-slate-500 text-[10px] inline-block transition-transform duration-200 {openSet.has(
                      s.session_id,
                    )
                      ? 'rotate-90'
                      : ''}">▶</span
                  >{short(s.session_id)}
                </span>
              </td>
              <td class="p-3 text-slate-400 font-mono text-xs"
                >{s.started_at}</td
              >
              <td class="p-3 text-right font-mono text-slate-400">{s.n_runs}</td
              >
              <td class="p-3 text-right font-mono"
                >{num(s.without_mm.correctness)}</td
              >
              <td class="p-3 text-right font-mono"
                >{num(s.with_mm.correctness)}</td
              >
              <td
                class="p-3 text-right font-mono {s.lift >= 0
                  ? 'text-emerald-400'
                  : 'text-red-400'}"
                >{s.lift == null ? "–" : (s.lift >= 0 ? "+" : "") + s.lift}</td
              >
              <td class="p-3 text-right font-mono"
                ><span class={tokClass(s.without_mm?.token_total, s.with_mm?.token_total)[0]}
                  >{fmtTokens(s.without_mm?.token_total)}</span
                ><span class={tokClass(s.without_mm?.token_total, s.with_mm?.token_total)[1]}
                  >/{fmtTokens(s.with_mm?.token_total)}</span
                ></td
              >
            </tr>
            {#if openSet.has(s.session_id)}
              <tr>
                <td colspan="7" class="p-0">
                  <div
                    transition:slide={{ duration: 200 }}
                    class="m-3 rounded-lg border border-slate-700 bg-slate-950 shadow-lg shadow-black/40 overflow-hidden"
                  >
                    {#if detail[s.session_id]?.loading || !detail[s.session_id]}
                      <div class="p-4 text-xs text-slate-500">
                        Loading cases…
                      </div>
                    {:else}
                      <table class="w-full text-sm">
                        <thead class="text-slate-500">
                          <tr>
                            <th class="text-left py-2 pl-10 pr-3 font-medium"
                              >Case</th
                            >
                            <!-- <th class="text-left py-2 px-3 font-medium">Type</th> -->
                            <th class="text-left py-2 px-3 font-medium"
                              >Without %</th
                            >
                            <th class="text-left py-2 px-3 font-medium"
                              >With %</th
                            >
                            <th class="text-left py-2 px-3 font-medium"
                              >Toks (wo/w)</th
                            >
                            <th class="text-left py-2 px-3 font-medium"
                              >mm cmds used</th
                            >
                            <th class="text-right py-2 px-3 font-medium">
                              Output
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {#each detail[s.session_id].cases as c (c.case_id)}
                            <tr class="border-t border-slate-800/60 align-top">
                              <td class="py-2 pl-10 pr-3">
                                <div class="text-slate-200">{c.case_id}</div>
                                <div
                                  class="flex gap-x-2 text-xs text-slate-600 items-center"
                                >
                                  <span>
                                    {c.archetype}
                                  </span>
                                  <span>
                                    |
                                    <!-- · -->
                                  </span>
                                  <span>
                                    {c.difficulty}
                                  </span>
                                </div>
                              </td>
                              <td class="py-2 px-3 text-left font-mono"
                                >{num(c.without_mm?.correctness)}</td
                              >
                              <td class="py-2 px-3 text-left font-mono"
                                >{num(c.with_mm?.correctness)}</td
                              >
                              <td class="py-2 px-3 text-xs font-mono">
                                <span class={tokClass(c.without_mm?.token_total, c.with_mm?.token_total)[0]}
                                  >{fmtTokens(c.without_mm?.token_total)}</span
                                ><span class={tokClass(c.without_mm?.token_total, c.with_mm?.token_total)[1]}
                                  >/{fmtTokens(c.with_mm?.token_total)}</span
                                >
                              </td>
                              <td
                                class="py-2 px-3 text-xs font-mono text-slate-400"
                                >{(c.with_mm?.mm_commands || []).join(", ") ||
                                  "–"}</td
                              >
                              <td class="py-2 px-3 text-right">
                                <button
                                  type="button"
                                  onclick={() =>
                                    openTx(s.session_id, c.case_id)}
                                  class="text-xs text-blue-400 hover:text-blue-300"
                                  >view</button
                                >
                              </td>
                            </tr>
                          {/each}
                        </tbody>
                      </table>
                    {/if}
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
    <p class="mt-3 text-xs leading-relaxed text-slate-500 max-w-4xl">
      <span class="text-slate-400">Table.</span> Each row is one session, a
      single benchmark pass over all cases for this cell.
      <span class="text-slate-400">Without %</span> and
      <span class="text-slate-400">With %</span> are the session's mean
      correctness with the agent's native tools versus with mm, and
      <span class="text-slate-400">Lift</span> is their difference in percentage
      points (positive favors mm). Click a row to expand its per-case breakdown.
    </p>
  </section>

  <section class="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-4">
    <h2
      class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3"
    >
      Correctness per case (all sessions)
    </h2>
    {#if d.cases?.length}
      <div class="relative w-full" style="height: {perCaseH}px">
        <Chart type="bar" data={perCase} options={perCaseOpts} />
      </div>
      <p class="mt-3 text-xs leading-relaxed text-slate-500 max-w-4xl">
        <span class="text-slate-400">Figure.</span> Mean correctness per case
        for this cell, without vs with mm, averaged over every run across all
        {d.sessions.length} session{d.sessions.length === 1 ? "" : "s"}. The gap
        between the two bars is mm's per-case lift.
      </p>
    {:else}
      <div class="text-slate-500 py-10 text-center text-sm">
        No case results yet.
      </div>
    {/if}
  </section>

  <dialog
    bind:this={txDialog}
    class="rounded-2xl border border-slate-700 bg-slate-900 text-slate-200 p-0 w-[min(90vw,56rem)] max-w-none backdrop:bg-black/60"
  >
    <div class="flex flex-col" style="min-height: 42vh; max-height: 82vh">
      <div
        class="flex items-center justify-between gap-3 px-5 py-3 border-b border-slate-800"
      >
        <div class="flex items-center gap-4 min-w-0">
          <div class="font-mono text-sm text-slate-300 truncate">{txCase}</div>
          <div class="inline-flex gap-1 text-xs">
            {#each [["transcript", "Result"], ["log", "Logs"], ["artifact", "Artifact"], ["spec", "Case spec"]] as [k, lbl]}
              <button
                type="button"
                onclick={() => (txTab = k)}
                class="px-2.5 py-1 rounded-md {txTab === k
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'}">{lbl}</button
              >
            {/each}
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {#if txTab !== "spec"}
            <div
              class="inline-flex rounded-lg border border-slate-700 overflow-hidden text-xs"
            >
              {#each [["without_mm", "Without mm"], ["with_mm", "With mm"]] as [k, lbl]}
                <button
                  type="button"
                  onclick={() => setArm(k)}
                  class="px-3 py-1 {txArm === k
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800'}">{lbl}</button
                >
              {/each}
            </div>
          {/if}
          <button
            type="button"
            onclick={() => txDialog.close()}
            class="text-slate-400 hover:text-slate-100 text-sm px-2">✕</button
          >
        </div>
      </div>
      <div class="overflow-auto p-5">
        {#if txTab === "transcript"}
          {#if txLoading}
            <div class="text-slate-500 text-sm">Loading result…</div>
          {:else if tx?.[txArm]}
            <pre
              class="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-200 select-text">{tx[
                txArm
              ].final_output || "(empty)"}</pre>
          {:else}
            <div class="text-slate-500 text-sm">No result for this arm.</div>
          {/if}
        {:else if txTab === "spec"}
          {#if !spec}
            <div class="text-slate-500 text-sm">Loading case spec…</div>
          {:else}
            <div class="space-y-4">
              <div>
                <div
                  class="text-xs uppercase tracking-widest text-slate-500 mb-1"
                >
                  Prompt
                </div>
                <pre
                  class="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-200 select-text">{spec.prompt ||
                    "(none)"}</pre>
              </div>
              <div>
                <div
                  class="text-xs uppercase tracking-widest text-slate-500 mb-1"
                >
                  Spec
                </div>
                <pre
                  class="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-300 select-text">{specRest}</pre>
              </div>
            </div>
          {/if}
        {:else if txTab === "artifact"}
          {#if artsLoading}
            <div class="text-slate-500 text-sm">Loading artifacts…</div>
          {:else if !arts.length}
            <div class="text-slate-500 h-[22vh] flex items-center text-sm">
              No artifact for this arm.
            </div>
          {:else}
            <div class="space-y-4">
              {#each arts as a (a)}
                <ArtifactView
                  url={artifactUrl(txSession, txCase, txArm, a)}
                  name={a}
                />
              {/each}
            </div>
          {/if}
        {:else if txLoading}
          <div class="text-slate-500 text-sm">Loading logs…</div>
        {:else}
          <div class="space-y-5">
            {#if tx?.[txArm]?.token_total != null}
              <div>
                <div
                  class="text-xs uppercase tracking-widest text-slate-500 mb-2"
                >
                  Tokens used
                </div>
                <div class="flex flex-wrap gap-3 text-xs">
                  <div
                    class="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                  >
                    <span class="text-slate-500">Total</span>
                    <span class="ml-2 font-mono text-slate-200"
                      >{fmtTokens(tx[txArm].token_total)}</span
                    >
                  </div>
                  {#if tx[txArm].token_usage}
                    {#each [["input_tokens", "Input"], ["output_tokens", "Output"], ["cache_read", "Cache read"], ["cache_write", "Cache write"], ["cost_usd", "Cost"]] as [k, lbl]}
                      {#if tx[txArm].token_usage[k]}
                        <div
                          class="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                        >
                          <span class="text-slate-500">{lbl}</span>
                          <span class="ml-2 font-mono text-slate-200"
                            >{k === "cost_usd"
                              ? "$" +
                                Number(tx[txArm].token_usage[k]).toFixed(4)
                              : fmtTokens(tx[txArm].token_usage[k])}</span
                          >
                        </div>
                      {/if}
                    {/each}
                  {/if}
                </div>
              </div>
            {/if}
            {#if txArm !== "without_mm" && tx?.[txArm]?.mm_token_total != null}
              <div>
                <div
                  class="text-xs uppercase tracking-widest text-slate-500 mb-2"
                >
                  mm cat tokens
                </div>
                <div class="flex flex-wrap gap-3 text-xs">
                  <div
                    class="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                  >
                    <span class="text-slate-500">Total</span>
                    <span class="ml-2 font-mono text-slate-200"
                      >{fmtTokens(tx[txArm].mm_token_total)}</span
                    >
                  </div>
                  {#if tx[txArm].mm_token_usage}
                    {#each [["input_tokens", "Input"], ["output_tokens", "Output"]] as [k, lbl]}
                      {#if tx[txArm].mm_token_usage[k]}
                        <div
                          class="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                        >
                          <span class="text-slate-500">{lbl}</span>
                          <span class="ml-2 font-mono text-slate-200"
                            >{fmtTokens(tx[txArm].mm_token_usage[k])}</span
                          >
                        </div>
                      {/if}
                    {/each}
                  {/if}
                </div>
              </div>
            {/if}
            <div>
              <div class="text-xs uppercase tracking-widest text-slate-500 mb-2">
                mm commands used ({txArm === "without_mm"
                  ? 0
                  : logEntries.length})
              </div>
              {#if txArm === "without_mm"}
                <div class="text-slate-600 text-xs">
                  mm is unavailable in the without-mm arm.
                </div>
              {:else if logEntries.length}
                <div class="space-y-2 font-mono text-xs">
                  {#each logEntries as e, i (i)}
                    <div>
                      <div class="text-slate-200 break-all">mm {e.args}</div>
                      <div
                        class={e.code === "0"
                          ? "text-slate-500"
                          : "text-red-400"}
                      >
                        exit {e.code} · {e.dur}s
                      </div>
                    </div>
                  {/each}
                </div>
              {:else}
                <div class="text-slate-600 text-xs">(none)</div>
              {/if}
            </div>
            <div>
              <div
                class="text-xs uppercase tracking-widest text-slate-500 mb-2"
              >
                stderr
              </div>
              {#if tx?.[txArm]?.stderr?.trim()}
                <pre
                  class="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-300 select-text">{tx[
                    txArm
                  ].stderr}</pre>
              {:else}
                <div class="text-slate-600 text-xs">(none)</div>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </div>
  </dialog>
{:else}
  <div class="text-slate-500 py-10">Loading…</div>
{/if}
