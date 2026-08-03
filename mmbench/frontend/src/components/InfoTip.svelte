<script>
  let { text, align = 'right' } = $props()
  let open = $state(false)
</script>
<svelte:window onclick={() => (open = false)} />
<span class="relative inline-flex items-center">
  <button type="button" aria-label="info"
    onclick={(e) => { e.stopPropagation(); open = !open }}
    class="inline-flex items-center justify-center w-4 h-4 rounded-full border border-slate-600 text-[10px] leading-none text-slate-400 hover:text-slate-100 hover:border-slate-400">i</button>
  {#if open}
    <span onclick={(e) => e.stopPropagation()}
      class="absolute z-30 top-6 {align === 'right' ? 'right-0' : 'left-0'} w-60 p-3 rounded-lg border border-slate-700 bg-slate-800 text-slate-200 text-xs font-normal normal-case text-left leading-relaxed shadow-xl">{text}</span>
  {/if}
</span>
