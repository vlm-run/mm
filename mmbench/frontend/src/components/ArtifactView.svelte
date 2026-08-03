<script>
  import { onMount } from "svelte";

  let { url, name } = $props();
  const ext = (name.split(".").pop() || "").toLowerCase();
  const IMG = ["png", "jpg", "jpeg", "webp", "gif", "avif", "bmp", "svg"];
  const VID = ["mp4", "mov", "webm", "mkv", "m4v"];
  const AUD = ["mp3", "wav", "m4a", "ogg", "flac", "aac"];
  const kind = IMG.includes(ext)
    ? "image"
    : VID.includes(ext)
      ? "video"
      : AUD.includes(ext)
        ? "audio"
        : ext === "pdf"
          ? "pdf"
          : "text";

  let text = $state(null);
  let err = $state(false);
  onMount(async () => {
    if (kind === "text") {
      try {
        const r = await fetch(url);
        text = await r.text();
      } catch {
        err = true;
      }
    }
  });
</script>

<div class="rounded-lg border border-slate-800 overflow-hidden">
  <div
    class="flex items-center justify-between px-3 py-2 bg-slate-900/60 text-xs"
  >
    <span class="font-mono text-slate-300 truncate">{name}</span>
    <a
      href={url}
      download={name}
      class="text-blue-400 hover:text-blue-300 shrink-0 ml-3">download</a
    >
  </div>
  <div class="p-3 bg-slate-950">
    {#if kind === "image"}
      <img src={url} alt={name} class="max-w-full max-h-[60vh] mx-auto" />
    {:else if kind === "video"}
      <!-- svelte-ignore a11y_media_has_caption -->
      <video src={url} controls class="max-w-full max-h-[60vh] mx-auto"></video>
    {:else if kind === "audio"}
      <audio src={url} controls class="w-full"></audio>
    {:else if kind === "pdf"}
      <iframe src={url} title={name} class="w-full h-[70vh] rounded bg-white"
      ></iframe>
    {:else if err}
      <div class="text-slate-500 text-sm">Could not load file.</div>
    {:else if text == null}
      <div class="text-slate-500 text-sm">Loading…</div>
    {:else}
      <pre
        class="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-200 select-text max-h-[60vh] overflow-auto">{text}</pre>
    {/if}
  </div>
</div>
