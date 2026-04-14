import { fmt, fmtCost } from "../lib/format";

/**
 * Uniform cost comparison table.
 *
 * Columns are always: Provider | Tokens | Cost | $/unit
 *
 * Props:
 *   rows      — array of { provider, accent, tokens, total, rate }
 *   unitLabel — label for the rate column (e.g. "$/min", "$/page")
 *   caption   — optional header caption
 */
export default function CostTable({ rows, unitLabel, caption }) {
  return (
    <div className="panel overflow-x-auto animate-slide-up">
      {caption && (
        <div className="px-4 py-2 border-b border-[var(--border)]">
          <span className="font-mono text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            {caption}
          </span>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th className="text-right">Tokens</th>
            <th className="text-right">Cost</th>
            <th className="text-right">{unitLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <span style={{ color: r.accent }} className="font-medium">
                  {r.provider}
                </span>
              </td>
              <td className="text-right font-mono">{fmt(r.tokens)}</td>
              <td className="text-right font-mono font-semibold" style={{ color: "var(--accent)" }}>
                {fmtCost(r.total)}
              </td>
              <td className="text-right font-mono text-[var(--text-muted)]">
                {fmtCost(r.rate)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
