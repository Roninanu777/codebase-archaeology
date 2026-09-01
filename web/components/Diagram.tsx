"use client";

import { shortDate, timeAgo } from "@/lib/format";

export interface ArcPoint {
  date: string | null;
  title: string;
  sub?: string;
  kind: "introduced" | "modified" | "hit";
  liveness?: number | null;
  repo?: string | null;
}

const REPO_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#f87171", "#e879f9"];

export function repoColor(repos: (string | null | undefined)[]): Record<string, string> {
  const names = [...new Set(repos.filter((r): r is string => !!r))].sort();
  const map: Record<string, string> = {};
  names.forEach((n, i) => {
    map[n] = REPO_COLORS[i % REPO_COLORS.length];
  });
  return map;
}

export function EvidenceArc({ points }: { points: ArcPoint[] }) {
  const dated = points.filter((p) => p.date && !Number.isNaN(new Date(p.date).getTime()));
  const undated = points.filter((p) => !p.date || Number.isNaN(new Date(p.date).getTime()));
  const ordered = [...dated].sort(
    (a, b) => new Date(a.date!).getTime() - new Date(b.date!).getTime()
  );
  if (ordered.length === 0) return null;
  if (ordered.length === 1) {
    ordered.push({ ...ordered[0] });
  }

  const W = 800;
  const H = 96;
  const PAD = 26;
  const times = ordered.map((p) => new Date(p.date!).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = max - min || 1;
  const xFor = (t: number) => PAD + ((t - min) / span) * (W - 2 * PAD);

  const repos = points.map((p) => p.repo);
  const colorMap = repoColor(repos);
  const multiRepo = Object.keys(colorMap).length > 1;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 pt-3 pb-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
        <line x1={PAD} y1={H / 2 - 8} x2={W - PAD} y2={H / 2 - 8} stroke="#3f3f46" strokeWidth="1.5" />
        <text x={PAD} y={H - 8} fill="#71717a" fontSize="11" fontFamily="var(--font-inter)">
          {shortDate(new Date(min).toISOString())}
        </text>
        <text x={W - PAD} y={H - 8} fill="#71717a" fontSize="11" textAnchor="end" fontFamily="var(--font-inter)">
          {shortDate(new Date(max).toISOString())}
        </text>
        {ordered.map((p, i) => {
          const x = xFor(times[i]);
          const isIntro = p.kind === "introduced";
          const alive = p.liveness === null || p.liveness === undefined ? true : p.liveness >= 0.34;
          const fill = p.kind === "introduced" ? "#f59e0b" : alive ? "#a1a1aa" : "#fb923c";
          const stroke = multiRepo && p.repo ? colorMap[p.repo] ?? "#52525b" : "#18181b";
          const hover = [p.title, p.sub, p.date ? timeAgo(p.date) : null, p.repo]
            .filter(Boolean)
            .join(" · ");
          return (
            <g key={`${p.title}-${i}`} className="cursor-help">
              <title>{hover}</title>
              {isIntro ? (
                <text x={x} y={H / 2 - 4} textAnchor="middle" fontSize="14" fill="#f59e0b">
                  ★
                </text>
              ) : (
                <circle
                  cx={x}
                  cy={H / 2 - 8}
                  r="5.5"
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={multiRepo ? 2 : 0}
                  opacity={p.kind === "hit" ? 0.85 : 1}
                />
              )}
            </g>
          );
        })}
        {undated.slice(0, 4).map((p, i) => (
          <g key={`u-${i}`} className="cursor-help">
            <title>{p.title}</title>
            <circle cx={PAD - 10 + i * 6} cy={H / 2 - 8} r="3" fill="#52525b" />
          </g>
        ))}
      </svg>
      {(multiRepo || points.some((p) => p.liveness !== null && p.liveness !== undefined)) && (
        <div className="flex flex-wrap items-center gap-3 px-1 pb-1 text-[10px] text-zinc-500">
          {multiRepo && (
            <span className="flex items-center gap-1.5">
              {Object.entries(colorMap).map(([name, color]) => (
                <span key={name} className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                  {name}
                </span>
              ))}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-zinc-400" /> alive
            <span className="h-2 w-2 rounded-full bg-orange-400" /> stale
            <span className="text-amber-400">★</span> introduced
          </span>
        </div>
      )}
    </div>
  );
}
