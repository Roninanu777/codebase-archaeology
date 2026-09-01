"use client";

import type { IndexStatus } from "@/lib/api";
import { Spinner } from "@/components/ui";

export type Mode = "auto" | "symbol" | "search";

const EXAMPLES = [
  "createRoot",
  "why does the scheduler use lanes?",
  "why was useMutableSource removed?",
  "how does reconciliation work?",
];

export function QueryBar({
  repos,
  repo,
  onRepoChange,
  query,
  onQueryChange,
  mode,
  onModeChange,
  busy,
  onTrace,
  onExplain,
}: {
  repos: IndexStatus[];
  repo: string;
  onRepoChange: (r: string) => void;
  query: string;
  onQueryChange: (q: string) => void;
  mode: Mode;
  onModeChange: (m: Mode) => void;
  busy: boolean;
  onTrace: () => void;
  onExplain: () => void;
}) {
  const current = repos.find((r) => r.name === repo);
  return (
    <div className="sticky top-0 z-10 -mx-6 bg-zinc-950/85 px-6 pb-3 pt-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <select
          value={repo}
          onChange={(e) => onRepoChange(e.target.value)}
          className="w-40 shrink-0 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 font-mono text-xs text-zinc-200 focus:border-amber-500/60 focus:outline-none"
        >
          {repos.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name}
            </option>
          ))}
          {repos.length === 0 && <option>no indexed repos</option>}
        </select>
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && onTrace()}
          placeholder="symbol, or a question…"
          className="min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3.5 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-amber-500/60 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
        />
        <button
          onClick={onTrace}
          disabled={busy || !query.trim()}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy && <Spinner />}
          Trace
        </button>
        <button
          onClick={onExplain}
          disabled={busy || !query.trim()}
          title="LLM synthesis — needs OPENROUTER_API_KEY on the backend"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-amber-500/40 px-4 py-2 text-sm font-medium text-amber-400 transition-colors hover:bg-amber-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy && <Spinner />}
          Explain
        </button>
      </div>

      <div className="mt-2 flex items-center gap-3">
        <div className="inline-flex shrink-0 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
          {(
            [
              { value: "auto", label: "auto" },
              { value: "symbol", label: "symbol" },
              { value: "search", label: "search" },
            ] as { value: Mode; label: string }[]
          ).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => onModeChange(opt.value)}
              className={`rounded-md px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                mode === opt.value
                  ? "bg-zinc-700/80 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto pb-0.5">
          <span className="shrink-0 text-[11px] text-zinc-600">try</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => onQueryChange(ex)}
              className="shrink-0 rounded-full border border-zinc-800 bg-zinc-900 px-2.5 py-0.5 text-[11px] text-zinc-400 transition-colors hover:border-zinc-600 hover:text-zinc-200"
            >
              {ex}
            </button>
          ))}
        </div>
        {current && (
          <span className="hidden shrink-0 font-mono text-[10px] text-zinc-600 sm:inline">
            {current.commits?.toLocaleString()} commits · {current.chunks?.toLocaleString()} chunks ·{" "}
            <span className={current.complete_at_head ? "text-emerald-500/90" : "text-amber-500/90"}>
              {current.complete_at_head ? "at HEAD" : "partial"}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
