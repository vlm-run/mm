<script>
  import Leaderboard from "./pages/Leaderboard.svelte";
  import CellDetail from "./pages/CellDetail.svelte";

  let route = $state("home");
  let params = $state({});
  function parse() {
    const path = (window.location.hash.slice(1) || "/").split("?")[0];
    const seg = path.split("/").filter(Boolean);
    if (seg[0] === "cell") {
      route = "cell";
      params = {
        assistant: decodeURIComponent(seg[1] || ""),
        profile: decodeURIComponent(seg[2] || ""),
      };
    } else {
      route = "home";
      params = {};
    }
  }
  $effect(() => {
    parse();
    const f = () => parse();
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  });
</script>

<header class="px-8 py-5 border-b border-slate-800 bg-slate-900">
  <a
    href="#/"
    class="text-lg font-semibold tracking-tight text-slate-100 no-underline"
    >mmbench</a
  >
  <span class="text-slate-500 text-sm ml-2">agents w/wo mm</span>
</header>
<main class="px-8 py-6 max-w-6xl mx-auto">
  {#if route === "cell"}
    <CellDetail assistant={params.assistant} profile={params.profile} />
  {:else}
    <Leaderboard />
  {/if}
</main>
