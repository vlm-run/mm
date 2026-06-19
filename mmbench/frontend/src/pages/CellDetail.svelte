<script>
  import { onMount } from "svelte";
  import Chart from "../components/Chart.svelte";
  import { fetchCell } from "../api.js";

  let { assistant, profile } = $props();
  let d = $state(null);
  onMount(async () => {
    d = await fetchCell(assistant, profile);
  });

  const num = (v, s = "") => (v == null ? "–" : v + s);
  const ax = { ticks: { color: "#94a3b8" }, grid: { color: "#1e293b" } };

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

  <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
    {#each [["Without mm", d.overall.without_mm.correctness, ""], ["With mm", d.overall.with_mm.correctness, ""], ["Lift", d.overall.lift, ""], ["Speedup", d.overall.speedup, "×"]] as [label, val, suf]}
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div class="text-xs uppercase tracking-widest text-slate-400">
          {label}
        </div>
        <div class="text-2xl font-semibold mt-1 font-mono">{num(val, suf)}</div>
      </div>
    {/each}
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
            >
          </tr></thead
        >
        <tbody>
          {#each d.sessions as s (s.session_id)}
            <tr
              class="border-t border-slate-800 hover:bg-slate-800/60 cursor-pointer"
              onclick={() =>
                (window.location.hash = `#/session/${s.session_id}`)}
            >
              <td class="p-3 text-blue-400 font-mono">{short(s.session_id)}</td>
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
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
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
{:else}
  <div class="text-slate-500 py-10">Loading…</div>
{/if}
