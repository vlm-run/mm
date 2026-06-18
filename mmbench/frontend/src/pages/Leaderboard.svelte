<script>
  import { onMount } from 'svelte'
  import MultiSelect from 'svelte-multiselect'
  import Chart from '../components/Chart.svelte'
  import InfoTip from '../components/InfoTip.svelte'
  import { fetchLeaderboard, fetchSessions } from '../api.js'

  let lb = $state([]), sessions = $state([])
  let assistants = $state([]), profiles = $state([])
  let selA = $state([]), selP = $state([])
  let howto = $state(null)
  let ready = $state(false)
  const LS = { a: 'mmbench.selA', p: 'mmbench.selP' }
  const loadSel = (key, opts) => {
    try { const s = JSON.parse(localStorage.getItem(key)); if (Array.isArray(s)) return s.filter((x) => opts.includes(x)) } catch {}
    return [...opts]
  }

  onMount(async () => {
    lb = await fetchLeaderboard()
    sessions = await fetchSessions()
    assistants = [...new Set(lb.map((r) => r.assistant))].sort()
    profiles = [...new Set(lb.map((r) => r.profile))].sort()
    selA = loadSel(LS.a, assistants)
    selP = loadSel(LS.p, profiles)
    ready = true
  })

  $effect(() => { selA; if (ready) localStorage.setItem(LS.a, JSON.stringify(selA)) })
  $effect(() => { selP; if (ready) localStorage.setItem(LS.p, JSON.stringify(selP)) })

  const rows = $derived(lb.filter((r) => selA.includes(r.assistant) && selP.includes(r.profile)))
  const cell = (r) => `${r.assistant}\\${r.profile}`
  const key = (s) => `${s.assistant}\\${s.profile}`
  const num = (v, s = '') => (v == null ? '–' : v + s)
  const href = (r) => `#/cell/${encodeURIComponent(r.assistant)}/${encodeURIComponent(r.profile)}`
  const PAL = ['#60a5fa', '#34d399', '#fbbf24', '#c084fc', '#f87171', '#22d3ee', '#f472b6', '#a3e635']
  const tick = { color: '#94a3b8' }
  const grid = { color: '#1e293b' }

  const barData = $derived({
    labels: rows.map(cell),
    datasets: [
      { label: 'Without mm', data: rows.map((r) => r.without_mm.correctness), backgroundColor: '#64748b' },
      { label: 'With mm', data: rows.map((r) => r.with_mm.correctness), backgroundColor: '#60a5fa' },
    ],
  })
  const barOpts = {
    scales: {
      x: { ticks: { ...tick, maxRotation: 90, minRotation: 0, autoSkip: false }, grid },
      y: { ticks: tick, grid, beginAtZero: true, max: 100 },
    },
    plugins: { legend: { labels: { color: '#cbd5e1' } } },
  }

  const trendData = $derived.by(() => {
    const keep = sessions.filter((s) => selA.includes(s.assistant) && selP.includes(s.profile))
    const byKey = {}
    keep.forEach((s) => { (byKey[key(s)] ||= []).push(s) })
    return { datasets: Object.entries(byKey).map(([k, arr], i) => ({ label: k, data: arr.map((s) => ({ x: s.started_at, y: s.with_mm_correctness })), borderColor: PAL[i % PAL.length], backgroundColor: PAL[i % PAL.length], pointRadius: 4, pointHoverRadius: 6, tension: 0.25 })) }
  })
  const trendOpts = {
    layout: { padding: { top: 8 } },
    scales: {
      x: {
        type: 'category',
        ticks: {
          ...tick,
          maxRotation: 0,
          autoSkip: true,
          callback: function (v) {
            const l = this.getLabelForValue(v)
            return typeof l === 'string' ? l.slice(5, 16).replace('T', ' ') : l
          },
        },
        grid,
      },
      y: { ticks: tick, grid, beginAtZero: true, max: 105 },
    },
    plugins: { legend: { labels: { color: '#cbd5e1' } } },
  }
</script>

<section class="mb-6">
  <h1 class="text-3xl font-bold tracking-tight">Does <span class="text-blue-400">mm</span> make agents better?</h1>
  <p class="mt-1 text-slate-400">Fast, multimodal context for agents &mdash; evaluated.</p>
  <p class="mt-3 text-slate-300 max-w-3xl leading-relaxed">
    mmbench measures whether the <code class="text-blue-300">mm</code> CLI makes AI agent
    harnesses (Claude Code, Codex, Gemini, opencode, &hellip;) more capable and faster, by
    running them on 20 hard, multi-turn tasks &mdash; retrieval, organization, and artifact
    creation &mdash; over nested folders of mixed media: images, video, audio, and PDFs. Each
    row is one <span class="text-slate-100">assistant / mm-profile</span> cell, averaged over its runs.
  </p>
  <button type="button" onclick={() => howto?.showModal()}
    class="mt-3 text-sm px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800">How it works</button>
</section>

<dialog bind:this={howto} class="rounded-2xl border border-slate-700 bg-slate-900 text-slate-200 p-0 max-w-lg backdrop:bg-black/60">
  <div class="p-6">
    <h2 class="text-lg font-semibold">How mmbench works</h2>
    <ol class="mt-3 text-sm text-slate-300 leading-relaxed list-decimal list-inside space-y-2">
      <li>Every task runs in an isolated sandbox copy of the dataset.</li>
      <li><b>Without mm</b>: the agent has only its native tools. <b>With mm</b>: <code class="text-blue-300">mm</code> on PATH + a one-page primer.</li>
      <li>Scored on correctness (deterministic checks + an LLM judge) and wall-clock speed.</li>
      <li><b>Lift</b> = with&minus;without correctness; <b>speedup</b> = without&divide;with time.</li>
    </ol>
    <div class="mt-5 text-right">
      <button type="button" onclick={() => howto.close()} class="text-sm px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white">Close</button>
    </div>
  </div>
</dialog>

<section class="mb-4 flex flex-wrap gap-3 items-end">
  <div class="min-w-56">
    <div class="text-xs text-slate-400 mb-1">Assistants</div>
    <MultiSelect bind:selected={selA} options={assistants}
      --sms-bg="#0f172a" --sms-text-color="#e2e8f0" --sms-border="1px solid #334155"
      --sms-border-radius="0.5rem" --sms-selected-bg="#1e3a8a" --sms-selected-text-color="#dbeafe"
      --sms-options-bg="#0f172a" --sms-li-active-bg="#1e293b" --sms-remove-btn-hover-color="#f87171" />
  </div>
  <div class="min-w-56">
    <div class="text-xs text-slate-400 mb-1">mm Profiles</div>
    <MultiSelect bind:selected={selP} options={profiles}
      --sms-bg="#0f172a" --sms-text-color="#e2e8f0" --sms-border="1px solid #334155"
      --sms-border-radius="0.5rem" --sms-selected-bg="#1e3a8a" --sms-selected-text-color="#dbeafe"
      --sms-options-bg="#0f172a" --sms-li-active-bg="#1e293b" --sms-remove-btn-hover-color="#f87171" />
  </div>
</section>

<section class="mb-8">
  <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2">Leaderboard</h2>
  {#if !rows.length}
    <div class="text-slate-500 py-10 text-center">No cells selected (or no runs yet).</div>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-slate-800">
      <table class="w-full text-sm">
        <thead class="bg-slate-900 text-slate-400">
          <tr>
            <th class="text-left p-3 w-8">#</th>
            <th class="text-left p-3">Assistant</th>
            <th class="text-left p-3">mm Profile</th>
            <th class="text-right p-3">Without %</th>
            <th class="text-right p-3">With %</th>
            <th class="p-3"><span class="flex items-center justify-end gap-1">Lift<InfoTip text="With-mm minus without-mm correctness, in percentage points. Positive means mm helped; negative means it hurt." /></span></th>
            <th class="p-3"><span class="flex items-center justify-end gap-1">Speedup<InfoTip text="Without-mm wall-clock time divided by with-mm time. Above 1× means the agent finished faster with mm." /></span></th>
            <th class="text-right p-3">Runs</th>
            <th class="p-3"><span class="flex items-center justify-end gap-1">Pass (with mm)<InfoTip text="Of the agent's with-mm case runs, how many scored at least 60% correctness (passes / total)." /></span></th>
            <th class="text-right p-3">Sessions</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as r (cell(r))}
            <tr class="border-t border-slate-800 hover:bg-slate-800/60 cursor-pointer" onclick={() => (window.location.hash = href(r))}>
              <td class="p-3 text-slate-500 font-mono">{r.rank}</td>
              <td class="p-3 text-blue-400 font-medium">{r.assistant}</td>
              <td class="p-3">
                <div class="text-slate-300">{r.profile}</div>
                <div class="text-xs text-slate-500 font-mono">{r.model || ''}</div>
                <div class="text-xs text-slate-600 font-mono break-all">{r.base_url || ''}</div>
              </td>
              <td class="p-3 text-right font-mono">{num(r.without_mm.correctness)}</td>
              <td class="p-3 text-right font-mono">{num(r.with_mm.correctness)}</td>
              <td class="p-3 text-right font-mono {r.lift >= 0 ? 'text-emerald-400' : 'text-red-400'}">{r.lift == null ? '–' : (r.lift >= 0 ? '+' : '') + r.lift}</td>
              <td class="p-3 text-right font-mono">{num(r.speedup, '×')}</td>
              <td class="p-3 text-right font-mono text-slate-400">{r.n_runs}</td>
              <td class="p-3 text-right font-mono">{r.with_mm.passes}/{r.with_mm.n}</td>
              <td class="p-3 text-right font-mono text-slate-400">{r.n_sessions}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<section class="grid lg:grid-cols-2 gap-4">
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 min-w-0">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Correctness: without vs with mm</h2>
    <div class="relative h-72 w-full"><Chart type="bar" data={barData} options={barOpts} /></div>
  </div>
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 min-w-0">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">With-mm correctness over time</h2>
    <div class="relative h-72 w-full"><Chart type="line" data={trendData} options={trendOpts} /></div>
  </div>
</section>
