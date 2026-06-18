<script>
  import { onMount } from 'svelte'
  import MultiSelect from 'svelte-multiselect'
  import Chart from '../components/Chart.svelte'
  import { fetchLeaderboard, fetchSessions } from '../api.js'

  let lb = $state([]), sessions = $state([])
  let assistants = $state([]), profiles = $state([])
  let selA = $state([]), selP = $state([])

  onMount(async () => {
    lb = await fetchLeaderboard()
    sessions = await fetchSessions()
    assistants = [...new Set(lb.map((r) => r.assistant))].sort()
    profiles = [...new Set(lb.map((r) => r.profile))].sort()
    selA = [...assistants]; selP = [...profiles]
  })

  const rows = $derived(lb.filter((r) => selA.includes(r.assistant) && selP.includes(r.profile)))
  const cell = (r) => `${r.assistant}/${r.profile}`
  const num = (v, s = '') => (v == null ? '–' : v + s)
  const href = (r) => `#/cell/${encodeURIComponent(r.assistant)}/${encodeURIComponent(r.profile)}`
  const PAL = ['#60a5fa', '#34d399', '#fbbf24', '#c084fc', '#f87171', '#22d3ee', '#f472b6', '#a3e635']
  const ax = { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }

  const barData = $derived({
    labels: rows.map(cell),
    datasets: [
      { label: 'Without mm', data: rows.map((r) => r.without_mm.correctness), backgroundColor: '#64748b' },
      { label: 'With mm', data: rows.map((r) => r.with_mm.correctness), backgroundColor: '#60a5fa' },
    ],
  })
  const barOpts = { scales: { x: ax, y: { ...ax, beginAtZero: true, max: 100 } }, plugins: { legend: { labels: { color: '#cbd5e1' } } } }

  const trendData = $derived.by(() => {
    const keep = sessions.filter((s) => selA.includes(s.assistant) && selP.includes(s.profile))
    const byKey = {}
    keep.forEach((s) => { (byKey[`${s.assistant}/${s.profile}`] ||= []).push(s) })
    return { datasets: Object.entries(byKey).map(([k, arr], i) => ({ label: k, data: arr.map((s) => ({ x: s.started_at, y: s.with_mm_correctness })), borderColor: PAL[i % PAL.length], backgroundColor: PAL[i % PAL.length], tension: 0.25 })) }
  })
  const trendOpts = { scales: { x: { ...ax, type: 'category' }, y: { ...ax, beginAtZero: true, max: 100 } }, plugins: { legend: { labels: { color: '#cbd5e1' } } } }
</script>

<section class="mb-8">
  <div class="rounded-2xl border border-slate-800 bg-gradient-to-br from-blue-950/40 to-slate-900 p-8">
    <h1 class="text-3xl font-bold tracking-tight">Does <span class="text-blue-400">mm</span> make agents better?</h1>
    <p class="mt-1 text-slate-400">Fast, multimodal context for agents &mdash; measured, not asserted.</p>
    <p class="mt-4 text-slate-300 max-w-3xl leading-relaxed">
      mmbench runs AI agent harnesses on hard, multi-turn tasks over real multimodal
      directories (images, video, audio, PDFs) and measures whether the <code class="text-blue-300">mm</code>
      CLI makes them more capable and faster.
    </p>
  </div>
  <div class="grid md:grid-cols-2 gap-4 mt-4">
    <div class="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400">What is mmbench</h2>
      <p class="mt-2 text-sm text-slate-300 leading-relaxed">
        A benchmark of agent harnesses (Claude Code, Codex, Gemini, opencode, &hellip;) on
        20 difficult, action-based tasks &mdash; retrieval, organization, and artifact
        creation &mdash; over nested folders of mixed media. Each cell is one
        <span class="text-slate-100">assistant / mm-profile</span> pair, averaged over its runs.
      </p>
    </div>
    <div class="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400">How it works</h2>
      <ol class="mt-2 text-sm text-slate-300 leading-relaxed list-decimal list-inside space-y-1">
        <li>Every task runs in an isolated sandbox copy of the dataset.</li>
        <li><b>Without mm</b>: the agent has only its native tools. <b>With mm</b>: <code class="text-blue-300">mm</code> on PATH + a one-page primer.</li>
        <li>Scored on correctness (deterministic checks + an LLM judge) and wall-clock speed.</li>
        <li><b>Lift</b> = with&minus;without correctness; <b>speedup</b> = without&divide;with time.</li>
      </ol>
    </div>
  </div>
</section>

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
            <th class="text-right p-3">Lift</th>
            <th class="text-right p-3">Speedup</th>
            <th class="text-right p-3">Runs</th>
            <th class="text-right p-3">Pass (with mm)</th>
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
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Correctness: without vs with mm</h2>
    <div class="h-72"><Chart type="bar" data={barData} options={barOpts} /></div>
  </div>
  <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">With-mm correctness over time</h2>
    <div class="h-72"><Chart type="line" data={trendData} options={trendOpts} /></div>
  </div>
</section>
