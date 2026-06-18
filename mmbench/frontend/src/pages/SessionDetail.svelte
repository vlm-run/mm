<script>
  import { onMount } from 'svelte'
  import { fetchSession } from '../api.js'

  let { id } = $props()
  let d = $state(null)
  onMount(async () => { d = await fetchSession(id) })
  const num = (v) => (v == null ? '–' : v)
</script>

{#if d && d.session}
  <a href={`#/cell/${encodeURIComponent(d.session.assistant)}/${encodeURIComponent(d.session.profile)}`} class="text-sm text-slate-400 hover:text-blue-400 no-underline">&larr; {d.session.assistant}/{d.session.profile}</a>
  <h1 class="text-2xl font-bold mt-2">Session <span class="font-mono text-slate-400 text-lg">{id.slice(0, 8)}</span></h1>
  <div class="text-xs text-slate-500 font-mono mt-1">{d.session.model || ''} · {d.session.base_url || ''}</div>
  <div class="text-xs text-slate-500 mt-1">{d.runs.length} run(s) · {d.session.started_at}</div>

  <section class="mt-6">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2">Cases ({d.cases.length})</h2>
    <div class="overflow-x-auto rounded-xl border border-slate-800">
      <table class="w-full text-sm">
        <thead class="bg-slate-900 text-slate-400"><tr>
          <th class="text-left p-3">Case</th><th class="text-left p-3">Type</th>
          <th class="text-right p-3">Without %</th><th class="text-right p-3">With %</th>
          <th class="text-left p-3">mm used</th>
        </tr></thead>
        <tbody>
          {#each d.cases as c (c.case_id)}
            <tr class="border-t border-slate-800 align-top">
              <td class="p-3"><div class="text-slate-100">{c.case_id}</div><div class="text-xs text-slate-500">{c.difficulty}</div></td>
              <td class="p-3"><span class="text-xs px-2 py-0.5 rounded-full border border-slate-700 text-slate-400">{c.archetype}</span></td>
              <td class="p-3 text-right font-mono">{num(c.without_mm?.correctness)}</td>
              <td class="p-3 text-right font-mono">{num(c.with_mm?.correctness)}</td>
              <td class="p-3 text-xs font-mono text-slate-400">{(c.with_mm?.mm_commands || []).join(', ') || '–'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{:else}
  <div class="text-slate-500 py-10">Loading…</div>
{/if}
