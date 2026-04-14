// OpenAI tile-based image token estimation (approximate).
export const TOKENS_PER_IMAGE_BASE = 85;
export const TOKENS_PER_TILE = 170;
export const TILE_PX = 512;

// Whisper-style audio token rate.
export const TOKENS_PER_AUDIO_SECOND = 25;

// PDF/text token estimation.
export const CHARS_PER_PAGE = 3000;
export const TOKENS_PER_CHAR = 0.75;

/** Estimate tokens for an image based on tile decomposition. */
export function imageTokens(w, h) {
  const tw = Math.max(1, Math.ceil(w / TILE_PX));
  const th = Math.max(1, Math.ceil(h / TILE_PX));
  return TOKENS_PER_IMAGE_BASE + tw * th * TOKENS_PER_TILE;
}
