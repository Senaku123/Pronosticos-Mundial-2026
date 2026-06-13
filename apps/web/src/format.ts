// Presentation helpers. Every probability is shown WITH context (addendum §6: honest uncertainty).

export function pct(p: number | null | undefined, digits = 1): string {
  if (p === null || p === undefined) return '—'
  return `${(p * 100).toFixed(digits)}%`
}

/**
 * Half-width of the 95% Monte Carlo confidence band for a probability estimated from
 * `n` independent simulations: 1.96 * sqrt(p(1-p)/n). This is the simulation error of the
 * estimate, NOT the real-world uncertainty of the event.
 */
export function monteCarloBand(p: number, n: number): number {
  if (n <= 0) return 0
  return 1.96 * Math.sqrt((p * (1 - p)) / n)
}

export function pctWithBand(p: number, n: number, digits = 1): string {
  return `${pct(p, digits)} ±${(monteCarloBand(p, n) * 100).toFixed(digits)}%`
}

/** Map a probability to a CSS background for heatmap cells (0 → dark, 1 → bright). */
export function heat(p: number, max: number): string {
  const t = max > 0 ? Math.min(1, p / max) : 0
  // teal scale on a dark background
  const alpha = 0.08 + 0.85 * t
  return `rgba(45, 212, 191, ${alpha.toFixed(3)})`
}
