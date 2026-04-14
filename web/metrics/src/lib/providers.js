/** LLM providers with input pricing ($/Mtok). */
const PROVIDERS = [
  { id: "claude-haiku", name: "Claude 4.5 Haiku", input: 0.8, accent: "#8b5cf6" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", input: 0.15, accent: "#10b981" },
  { id: "gemini-flash", name: "Gemini 2.5 Flash", input: 0.15, accent: "#3b82f6" },
  { id: "qwen-vl-72b", name: "Qwen3-VL 72B", input: 0.4, accent: "#f59e0b" },
];

export default PROVIDERS;

/** Compute cost in dollars for a given token count and provider. */
export function cost(tokens, provider) {
  return (tokens * provider.input) / 1_000_000;
}
