import type { MergeTable as MergeTableData } from "@/lib/types";

/**
 * Lane-Merge Table: one row per symbol with rating + lanes (T26). Renders
 * the merge_table artifact produced by a component-graph run. Falls back to
 * a helpful empty state when no merge table exists.
 */
export function MergeTable({ table }: { table: MergeTableData | null | undefined }) {
  if (!table || table.rows.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 text-center text-sm text-slate-500">
        No merge-table rows yet — run a component graph to see lane-merged results here.
      </div>
    );
  }

  const columns = table.columns;
  return (
    <div className="overflow-auto rounded-lg border border-slate-800">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900 text-slate-500">
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 font-medium capitalize">
                {c.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r) => (
            <tr key={String(r.symbol)} className="border-b border-slate-800/60 text-slate-300">
              {columns.map((c) => (
                <td key={c} className="px-3 py-2">
                  {c === "symbol" ? (
                    <span className="font-mono font-medium text-slate-100">{String(r[c])}</span>
                  ) : c === "rating" ? (
                    <span className="font-medium text-cyan-300">
                      {typeof r[c] === "number" ? "★".repeat(Math.round(r[c] as number)) : String(r[c] ?? "")}
                    </span>
                  ) : (
                    <span>{formatCell(r[c])}</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return value % 1 === 0 ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
