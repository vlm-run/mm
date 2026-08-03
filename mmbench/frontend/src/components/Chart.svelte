<script>
  import { Chart, registerables } from 'chart.js'
  import { onMount } from 'svelte'
  Chart.register(...registerables)
  let { type, data, options = {} } = $props()
  let canvas = $state(null)
  let chart = null
  $effect(() => {
    if (!canvas) return
    const opts = { responsive: true, maintainAspectRatio: false, ...options }
    if (chart) { chart.data = data; chart.options = opts; chart.update() }
    else chart = new Chart(canvas, { type, data, options: opts })
  })
  onMount(() => () => chart?.destroy())
</script>
<canvas bind:this={canvas}></canvas>
