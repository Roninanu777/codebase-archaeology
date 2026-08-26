"use client";

import type { SearchHit } from "@/lib/api";
import { hitUrl, repoShort, shortDate } from "@/lib/format";
import { LivenessChip, RepoBadge, TypeIcon } from "@/components/ui";

export function HitList({ hits }: { hits: SearchHit[] }) {
  return (
    <ol className="divide-y divide-zinc-800/70 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
      {hits.map((hit, i) => (
        <li key={`${hit.sha}-${i}`} className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-zinc-900/70">
          <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-xs text-zinc-600">
            {i + 1}
          </span>
          <span className="mt-0.5"><TypeIcon sha={hit.sha} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <a
                href={hitUrl(hit)}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-xs text-blue-400 underline-offset-2 hover:underline"
              >
                {hit.sha}
              </a>
              {hit.authored_at && (
                <span className="text-xs text-zinc-600">{shortDate(hit.authored_at)}</span>
              )}
              <LivenessChip score={hit.liveness_score} stale={hit.stale} />
              <RepoBadge repo={hit.repo} />
            </div>
            <p className="mt-1 truncate text-sm text-zinc-300" title={hit.title}>
              {hit.title}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
