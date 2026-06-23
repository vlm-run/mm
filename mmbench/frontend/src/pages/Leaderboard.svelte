<script>
  import { onMount } from "svelte";
  import MultiSelect from "svelte-multiselect";
  import Chart from "../components/Chart.svelte";
  import InfoTip from "../components/InfoTip.svelte";
  import { fetchLeaderboard, fetchSessions, fetchCaseBreakdown } from "../api.js";

  let lb = $state([]),
    sessions = $state([]),
    cb = $state({ cases: [], rows: [] });
  let assistants = $state([]),
    profiles = $state([]),
    caseIds = $state([]);
  let selA = $state([]),
    selP = $state([]),
    selCases = $state([]);
  let howto = $state(null);
  let ready = $state(false);
  const LS = { a: "mmbench.selA", p: "mmbench.selP", c: "mmbench.selCases.v3" };
  const loadSel = (key, opts, dflt = opts) => {
    try {
      const s = JSON.parse(localStorage.getItem(key));
      if (Array.isArray(s)) return s.filter((x) => opts.includes(x));
    } catch {}
    return [...dflt];
  };

  onMount(async () => {
    lb = await fetchLeaderboard();
    sessions = await fetchSessions();
    cb = await fetchCaseBreakdown();
    assistants = [...new Set(lb.map((r) => r.assistant))].sort();
    profiles = [...new Set(lb.map((r) => r.profile))].sort();
    caseIds = cb.cases.map((c) => c.case_id);
    selA = loadSel(LS.a, assistants);
    selP = loadSel(LS.p, profiles);
    selCases = loadSel(LS.c, caseIds, caseIds.slice(0, 8));
    ready = true;
  });

  $effect(() => {
    selA;
    if (ready) localStorage.setItem(LS.a, JSON.stringify(selA));
  });
  $effect(() => {
    selP;
    if (ready) localStorage.setItem(LS.p, JSON.stringify(selP));
  });
  $effect(() => {
    selCases;
    if (ready) localStorage.setItem(LS.c, JSON.stringify(selCases));
  });

  const rows = $derived(
    lb.filter((r) => selA.includes(r.assistant) && selP.includes(r.profile)),
  );

  let sortKey = $state("with_mm"),
    sortDir = $state("desc");
  const sortVal = (r, k) =>
    k === "without_mm"
      ? r.without_mm.correctness
      : k === "with_mm"
        ? r.with_mm.correctness
        : k === "lift"
          ? r.lift
          : k === "speedup"
            ? r.speedup
            : k === "pass"
              ? r.with_mm.n
                ? r.with_mm.passes / r.with_mm.n
                : null
              : k === "tokens"
                ? r.with_mm.token_total
                : null;
  const setSort = (k) => {
    if (sortKey === k) sortDir = sortDir === "desc" ? "asc" : "desc";
    else {
      sortKey = k;
      sortDir = "desc";
    }
  };
  const caret = (k) => (sortKey === k ? (sortDir === "desc" ? "▼" : "▲") : ""); // ↕
  const caretCls = (k) => (sortKey === k ? "text-blue-400" : "text-slate-600");
  const sortedRows = $derived.by(() => {
    const arr = [...rows];
    arr.sort((a, b) => {
      const va = sortVal(a, sortKey),
        vb = sortVal(b, sortKey);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "desc" ? vb - va : va - vb;
    });
    return arr;
  });
  const cell = (r) => `${r.assistant}\\${r.profile}`;
  const key = (s) => `${s.assistant}\\${s.profile}`;
  const num = (v, s = "") => (v == null ? "–" : v + s);
  const fmtTokens = (v) =>
    v == null ? "–" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "k" : String(v);
  const href = (r) =>
    `#/cell/${encodeURIComponent(r.assistant)}/${encodeURIComponent(r.profile)}`;
  const PAL = [
    "#60a5fa",
    "#34d399",
    "#fbbf24",
    "#c084fc",
    "#f87171",
    "#22d3ee",
    "#f472b6",
    "#a3e635",
  ];
  const tick = { color: "#94a3b8" };
  const grid = { color: "#1e293b" };
  const fade = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  const barData = $derived({
    labels: rows.map(cell),
    datasets: [
      {
        label: "Without mm",
        data: rows.map((r) => r.without_mm.correctness),
        backgroundColor: "#64748b",
      },
      {
        label: "With mm",
        data: rows.map((r) => r.with_mm.correctness),
        backgroundColor: "#60a5fa",
      },
    ],
  });
  const barOpts = {
    scales: {
      x: {
        ticks: { ...tick, maxRotation: 90, minRotation: 0, autoSkip: false },
        grid,
      },
      y: { ticks: tick, grid, beginAtZero: true, max: 100 },
    },
    plugins: { legend: { labels: { color: "#cbd5e1" } } },
  };

  const trendData = $derived.by(() => {
    const keep = sessions.filter(
      (s) => selA.includes(s.assistant) && selP.includes(s.profile),
    );
    const byKey = {};
    keep.forEach((s) => {
      (byKey[key(s)] ||= []).push(s);
    });
    return {
      datasets: Object.entries(byKey).map(([k, arr], i) => {
        arr.sort((a, b) => (a.started_at < b.started_at ? -1 : 1));
        return {
          label: k,
          data: arr.map((s, j) => ({ x: j + 1, y: s.with_mm_correctness })),
          borderColor: PAL[i % PAL.length],
          backgroundColor: PAL[i % PAL.length],
          pointRadius: 4,
          pointHoverRadius: 6,
          tension: 0.25,
        };
      }),
    };
  });
  const trendOpts = {
    layout: { padding: { top: 8 } },
    scales: {
      x: {
        type: "linear",
        min: 1,
        offset: true,
        title: { display: true, text: "Session #", color: "#94a3b8" },
        ticks: { ...tick, stepSize: 1, precision: 0 },
        grid,
      },
      y: { ticks: tick, grid, beginAtZero: true, max: 105 },
    },
    plugins: { legend: { labels: { color: "#cbd5e1" } } },
  };

  const cmpMap = $derived.by(() => {
    const m = {};
    cb.rows.forEach((r) => {
      m[`${r.assistant}\\${r.profile}\\${r.case_id}`] = r;
    });
    return m;
  });
  const cmpData = $derived.by(() => {
    const datasets = [];
    rows.forEach((r, i) => {
      const col = PAL[i % PAL.length];
      const stack = cell(r);
      const at = (key) =>
        selCases.map((cid) => {
          const m = cmpMap[`${r.assistant}\\${r.profile}\\${cid}`];
          return m ? m[key] : null;
        });
      datasets.push({
        label: `${cell(r)} (w/o)`,
        data: at("without_mm"),
        backgroundColor: fade(col, 0.28),
        stack,
        order: 0,
        barPercentage: 0.92,
        categoryPercentage: 0.78,
      });
      datasets.push({
        label: cell(r),
        data: at("with_mm"),
        backgroundColor: col,
        stack,
        order: 1,
        barPercentage: 0.5,
        categoryPercentage: 0.78,
      });
    });
    return { labels: selCases, datasets };
  });
  const cmpOpts = {
    scales: {
      x: {
        stacked: false,
        ticks: { ...tick, maxRotation: 90, minRotation: 45, autoSkip: false },
        grid,
      },
      y: { stacked: false, ticks: tick, grid, beginAtZero: true, max: 100 },
    },
    plugins: {
      legend: {
        labels: { color: "#cbd5e1", filter: (i) => i.datasetIndex % 2 === 1 },
      },
    },
  };
</script>

<section class="mb-6">
  <h1 class="text-3xl font-bold tracking-tight">
    Does <span class="text-blue-400">mm</span> make universal assistants better?
  </h1>
  <p class="mt-1 text-slate-400">
    Fast, multimodal context for agents &mdash; evaluated.
  </p>
  <p class="mt-3 text-slate-300 max-w-3xl leading-relaxed">
    mmbench measures whether the <code class="text-blue-300">mm</code> CLI makes
    AI agent harnesses (Claude Code, Codex, Gemini, openclaw, &hellip;) more
    capable and faster, by running them on 20 hard, multi-turn tasks &mdash;
    retrieval, organization, and artifact creation &mdash; over nested folders
    of mixed media: images, video, audio, and PDFs. Each row is one
    <span class="text-slate-100">assistant / mm-profile</span> cell, averaged over
    its runs.
  </p>
  <button
    type="button"
    onclick={() => howto?.showModal()}
    class="mt-3 text-sm px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800"
    >How it works</button
  >
</section>

<dialog
  bind:this={howto}
  class="rounded-2xl border border-slate-700 bg-slate-900 text-slate-200 p-0 max-w-lg backdrop:bg-black/60"
>
  <div class="p-6">
    <h2 class="text-lg font-semibold">How mmbench works</h2>
    <ol
      class="mt-3 text-sm text-slate-300 leading-relaxed list-decimal list-inside space-y-2"
    >
      <li>Every task runs in an isolated sandbox copy of the dataset.</li>
      <li>
        <b>Without mm</b>: the agent has only its native tools. <b>With mm</b>:
        <code class="text-blue-300">mm</code> on PATH + a one-page primer.
      </li>
      <li>
        Scored on correctness (deterministic checks + an LLM judge) and
        wall-clock speed.
      </li>
      <li>
        <b>Lift</b> = with&minus;without correctness; <b>speedup</b> = without&divide;with
        time.
      </li>
    </ol>
    <div class="mt-5 text-right">
      <button
        type="button"
        onclick={() => howto.close()}
        class="text-sm px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white"
        >Close</button
      >
    </div>
  </div>
</dialog>

<section class="mb-4 flex flex-wrap gap-3 items-end">
  <div class="min-w-56">
    <div class="text-xs text-slate-400 mb-1">Assistants</div>
    {#if assistants.length}
      <MultiSelect
        bind:selected={selA}
        options={assistants}
        --sms-bg="#0f172a"
        --sms-text-color="#e2e8f0"
        --sms-border="1px solid #334155"
        --sms-border-radius="0.5rem"
        --sms-selected-bg="#1e3a8a"
        --sms-selected-text-color="#dbeafe"
        --sms-options-bg="#0f172a"
        --sms-li-active-bg="#1e293b"
        --sms-remove-btn-hover-color="#f87171"
      />
    {/if}
  </div>
  <div class="min-w-56">
    <div class="text-xs text-slate-400 mb-1">mm Profiles</div>
    {#if profiles.length}
      <MultiSelect
        bind:selected={selP}
        options={profiles}
        --sms-bg="#0f172a"
        --sms-text-color="#e2e8f0"
        --sms-border="1px solid #334155"
        --sms-border-radius="0.5rem"
        --sms-selected-bg="#1e3a8a"
        --sms-selected-text-color="#dbeafe"
        --sms-options-bg="#0f172a"
        --sms-li-active-bg="#1e293b"
        --sms-remove-btn-hover-color="#f87171"
      />
    {/if}
  </div>
</section>

<section class="mb-8">
  <h2
    class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2"
  >
    Leaderboard
  </h2>
  {#if !rows.length}
    <div class="text-slate-500 py-10 text-center">
      No cells selected (or no runs yet).
    </div>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-slate-800">
      <table class="w-full text-sm">
        <thead class="bg-slate-900 text-slate-400">
          <tr>
            <th class="text-left p-3 w-8">#</th>
            <th class="text-left p-3">Assistant</th>
            <th class="text-left p-3">mm Profile</th>
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("without_mm")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >Without %<span
                    class="w-2 text-[10px] {caretCls('without_mm')}"
                    >{caret("without_mm")}</span
                  ></button
                ></span
              ></th
            >
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("with_mm")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >With %<span class="w-2 text-[10px] {caretCls('with_mm')}"
                    >{caret("with_mm")}</span
                  ></button
                ></span
              ></th
            >
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("lift")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >Lift<span class="w-2 text-[10px] {caretCls('lift')}"
                    >{caret("lift")}</span
                  ></button
                ><InfoTip
                  text="With-mm minus without-mm correctness, in percentage points. Positive means mm helped; negative means it hurt."
                /></span
              ></th
            >
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("speedup")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >Speedup<span class="w-2 text-[10px] {caretCls('speedup')}"
                    >{caret("speedup")}</span
                  ></button
                ><InfoTip
                  text="Without-mm wall-clock time divided by with-mm time. Above 1× means the agent finished faster with mm."
                /></span
              ></th
            >
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("pass")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >Pass (mm)<span
                    class="w-2 text-[10px] {caretCls('pass')}"
                    >{caret("pass")}</span
                  ></button
                ><InfoTip
                  text="Of the agent's with-mm case runs, how many scored at least 60% correctness (passes / total)."
                /></span
              ></th
            >
            <th class="p-3"
              ><span class="flex items-center justify-end gap-1"
                ><button
                  type="button"
                  onclick={() => setSort("tokens")}
                  class="inline-flex items-center gap-1 cursor-pointer select-none hover:text-slate-200"
                  >Toks (w/wo)<span
                    class="w-2 text-[10px] {caretCls('tokens')}"
                    >{caret("tokens")}</span
                  ></button
                ><InfoTip
                  text="Mean total tokens (input + output + reasoning) per case run, with mm / without mm. Sorted by with-mm; a lower number means the agent used less context to achieve its result."
                /></span
              ></th
            >
            <th class="text-right p-3">Sessions</th>
            <th class="text-right p-3">Runs</th>
          </tr>
        </thead>
        <tbody>
          {#each sortedRows as r, i (cell(r))}
            <tr
              class="border-t border-slate-800 hover:bg-slate-800/60 cursor-pointer"
              onclick={() => (window.location.hash = href(r))}
            >
              <td class="p-3 text-slate-500 font-mono">{i + 1}</td>
              <td class="p-3 text-blue-400 font-medium">{r.assistant}</td>
              <td class="p-3">
                <div class="text-slate-300">{r.profile}</div>
                <div class="text-xs text-slate-500 font-mono">
                  {r.model || ""}
                </div>
                <div class="text-xs text-slate-600 font-mono break-all">
                  {r.base_url || ""}
                </div>
              </td>
              <td class="p-3 text-right font-mono"
                >{num(r.without_mm.correctness)}</td
              >
              <td class="p-3 text-right font-mono"
                >{num(r.with_mm.correctness)}</td
              >
              <td
                class="p-3 text-right font-mono {r.lift >= 0
                  ? 'text-emerald-400'
                  : 'text-red-400'}"
                >{r.lift == null ? "–" : (r.lift >= 0 ? "+" : "") + r.lift}</td
              >
              <td class="p-3 text-right font-mono">{num(r.speedup, "×")}</td>
              <td class="p-3 text-right font-mono"
                >{r.with_mm.passes}/{r.with_mm.n}</td
              >
              <td class="p-3 text-right font-mono"
                ><span class="text-slate-300"
                  >{fmtTokens(r.with_mm.token_total)}</span
                ><span class="text-slate-500"
                  >/{fmtTokens(r.without_mm.token_total)}</span
                ></td
              >
              <td class="p-3 text-right font-mono text-slate-400"
                >{r.n_sessions}</td
              >
              <td class="p-3 text-right font-mono text-slate-400">{r.n_runs}</td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="mt-3 text-xs leading-relaxed text-slate-500 max-w-4xl">
      <span class="text-slate-400">Table 1.</span> Each row is one
      <span class="text-slate-400">assistant / mm-profile</span> cell.
      <span class="text-slate-400">Without %</span> and
      <span class="text-slate-400">With %</span> are mean correctness (0 to 100, a
      50/50 blend of deterministic checks and an LLM judge) for the agent running
      with only its native tools versus with the <code class="text-blue-300">mm</code
      > CLI on PATH, averaged over every case, run, and session.
      <span class="text-slate-400">Lift</span> is the difference (With minus Without)
      in percentage points; positive means mm helped.
      <span class="text-slate-400">Speedup</span> is without-mm wall-clock time divided
      by with-mm time, so above 1× means the agent finished faster with mm.
      <span class="text-slate-400">Pass (mm)</span> is the share of with-mm case
      runs scoring at least 60% correctness.
      <span class="text-slate-400">Toks (w/wo)</span> is the mean total tokens
      (input + output + reasoning) per case run, with mm / without mm.
      <span class="text-slate-400">Sessions</span> and
      <span class="text-slate-400">Runs</span> report how many benchmark passes back
      each average. Rows are sortable; click any row to drill into a cell.
    </p>
  {/if}
</section>

<section class="grid lg:grid-cols-2 gap-4">
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 min-w-0">
    <h2
      class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3"
    >
      Correctness: without vs with mm
    </h2>
    <div class="relative h-72 w-full">
      <Chart type="bar" data={barData} options={barOpts} />
    </div>
  </div>
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 min-w-0">
    <h2
      class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3"
    >
      With-mm correctness over sessions
    </h2>
    <div class="relative h-72 w-full">
      <Chart type="line" data={trendData} options={trendOpts} />
    </div>
  </div>
</section>

<section class="mt-4 rounded-xl border border-slate-800 bg-slate-900 p-4 min-w-0">
  <div class="flex flex-wrap items-end justify-between gap-3 mb-3">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400">
      Correctness per case
    </h2>
    <div class="min-w-72">
      <div class="text-xs text-slate-400 mb-1">Cases</div>
      {#if caseIds.length}
        <MultiSelect
          bind:selected={selCases}
          options={caseIds}
          --sms-bg="#0f172a"
          --sms-text-color="#e2e8f0"
          --sms-border="1px solid #334155"
          --sms-border-radius="0.5rem"
          --sms-selected-bg="#334155"
          --sms-selected-text-color="#cbd5e1"
          --sms-options-bg="#0f172a"
          --sms-li-active-bg="#1e293b"
          --sms-remove-btn-hover-color="#f87171"
        />
      {/if}
    </div>
  </div>
  {#if !rows.length}
    <div class="text-slate-500 py-10 text-center text-sm">
      Select at least one cell (filters above).
    </div>
  {:else}
    {#if selCases.length}
      <div class="relative h-96 w-full">
        <Chart type="bar" data={cmpData} options={cmpOpts} />
      </div>
      <p class="mt-3 text-xs leading-relaxed text-slate-500 max-w-4xl">
        <span class="text-slate-400">Figure.</span> Mean correctness per case for each
        selected cell, averaged over all sessions and runs. Each column shows two
        values for the same cell: the solid bar is
        <span class="text-slate-300">with mm</span>, the faint bar behind it is
        <span class="text-slate-300">without mm</span> (native tools only), so the
        gap between them is mm's per-case lift. Cells come from the assistant /
        mm-profile filters above; pick the cases to chart with the selector.
      </p>
    {:else}
      <div class="text-slate-500 py-10 text-center text-sm">
        Select cases above to chart them. The full table is below.
      </div>
    {/if}

    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-800">
      <table class="w-full text-sm border-separate border-spacing-0">
        <thead class="bg-slate-900 text-slate-400">
          <tr>
            <th
              class="text-left p-3 sticky left-0 z-10 bg-slate-900 border-b border-slate-800"
              >Case</th
            >
            {#each rows as r (cell(r))}
              <th class="p-3 text-right whitespace-nowrap border-b border-slate-800">
                <div class="text-slate-300">{r.assistant}</div>
                <div class="text-xs text-slate-500 font-mono">{r.profile}</div>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each caseIds as cid (cid)}
            <tr class="hover:bg-slate-800/40">
              <td
                class="p-3 font-mono text-slate-300 whitespace-nowrap sticky left-0 z-10 bg-slate-950 border-t border-slate-800"
                >{cid}</td
              >
              {#each rows as r (cell(r))}
                {@const m = cmpMap[`${r.assistant}\\${r.profile}\\${cid}`]}
                <td class="p-3 text-right font-mono border-t border-slate-800">
                  {#if m && (m.with_mm != null || m.without_mm != null)}
                    <span class="text-slate-100">{num(m.with_mm)}</span><span
                      class="text-slate-500">/{num(m.without_mm)}</span
                    >
                  {:else}
                    <span class="text-slate-500">–</span>
                  {/if}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="mt-3 text-xs leading-relaxed text-slate-500 max-w-4xl">
      <span class="text-slate-400">Table 2.</span> Per-case correctness for
      <span class="text-slate-300">all {caseIds.length} cases</span> (independent of
      the chart's case selector), in
      <span class="text-slate-300">with mm / without mm</span> form (e.g. 85/79),
      cases down the rows and assistant / mm-profile cells across the columns.
      Scroll horizontally to compare more cells.
    </p>
  {/if}
</section>
