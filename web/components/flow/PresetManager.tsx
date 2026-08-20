"use client";

import { useEffect, useState } from "react";
import {
  listComponentTemplates,
  listDefinitions,
  saveComponentTemplate,
  deleteComponentTemplate,
} from "@/lib/api";
import type { Family } from "@/lib/flow";
import { FAMILY_LABELS } from "@/lib/flow";

export interface ScannerPreset {
  id: string;
  name: string;
  kind: "starter" | "custom";
  family?: Family;
  variables?: Record<string, string | number | boolean>;
}

/** Builtin starters for the new families (no seeded DB definition yet). */
const BUILTIN_STARTERS: ScannerPreset[] = [
  {
    id: "zhao-realtime",
    name: "照妖鏡 realtime",
    kind: "starter",
    family: "zhao",
    variables: { zhao_variant: "realtime" },
  },
  {
    id: "zhao-daily",
    name: "照妖鏡 daily",
    kind: "starter",
    family: "zhao",
    variables: { zhao_variant: "daily" },
  },
  {
    id: "premarket-grep",
    name: "Premarket grep",
    kind: "starter",
    family: "premarket",
  },
];

/**
 * Scanner presets: the three seeded daily definitions are starter presets
 * (family only); saved component templates are "my settings" (full vars).
 * zhao/premarket starters are builtin (frontend-only) until seeded definitions exist.
 */
export function PresetManager({
  family,
  currentVars,
  onApply,
}: {
  family: Family;
  currentVars: Record<string, string | number | boolean>;
  onApply: (family: Family, vars: Record<string, string | number | boolean>) => void;
}) {
  const [presets, setPresets] = useState<ScannerPreset[]>([]);
  const [saveName, setSaveName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const reload = () => {
    Promise.all([listComponentTemplates(), listDefinitions()])
      .then(([templates, definitions]) => {
        const starters: ScannerPreset[] = definitions
          .filter((d) => /^Daily (VCP|BO|EP) Scan$/.test(d.name))
          .map((d) => {
            const familyMatch = /^Daily (VCP|BO|EP) Scan$/.exec(d.name);
            const fam = familyMatch
              ? ({ VCP: "vcp", BO: "bo", EP: "ep" }[familyMatch[1]] as Family)
              : undefined;
            return { id: d.id, name: d.name, kind: "starter", family: fam };
          });
        const customs: ScannerPreset[] = templates
          .filter((t) => t.component_id === "scanner")
          .map((t) => ({ id: t.id, name: t.name, kind: "custom", variables: t.variables }));
        setPresets([...BUILTIN_STARTERS, ...starters, ...customs]);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function handleSave() {
    if (!saveName.trim()) return;
    setError(null);
    try {
      await saveComponentTemplate({
        name: saveName.trim(),
        component_id: "scanner",
        variables: { family, ...currentVars },
      });
      setSaveName("");
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteComponentTemplate(id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="relative">
      <button type="button" className="btn-ghost" onClick={() => setOpen((v) => !v)}>
        Presets
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-md border border-ink-700 bg-ink-900 p-3 shadow-xl shadow-black/40">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Presets</h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-xs text-slate-600 hover:text-slate-300"
            >
              ✕
            </button>
          </div>

          {error && <p className="mt-2 text-xs text-down-500">{error}</p>}

          <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
            {presets.length === 0 && (
              <p className="py-3 text-center text-xs text-slate-600">No presets yet.</p>
            )}
            {presets.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between gap-2 rounded border border-ink-800 bg-ink-850 px-2.5 py-1.5"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  title="Apply preset"
                  onClick={() => {
                    onApply(p.family ?? family, p.variables ?? {});
                    setOpen(false);
                  }}
                >
                  <div className="truncate text-sm text-slate-200">{p.name}</div>
                  <div className="text-2xs uppercase tracking-wider text-slate-600">
                    {p.kind === "starter" ? `starter · ${p.family ? FAMILY_LABELS[p.family] : "—"}` : "my settings"}
                  </div>
                </button>
                {p.kind === "custom" && (
                  <button
                    type="button"
                    onClick={() => handleDelete(p.id)}
                    className="text-xs text-slate-600 hover:text-down-500"
                    title="Delete preset"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="mt-3 flex items-center gap-2 border-t border-ink-800 pt-3">
            <input
              className="field px-2 py-1.5 text-sm"
              placeholder="Save current as…"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSave()}
            />
            <button type="button" className="btn-ghost px-2.5 py-1.5 text-sm" onClick={handleSave}>
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
