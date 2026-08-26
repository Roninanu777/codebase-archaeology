"use client";

import type { EvidenceCommit } from "@/lib/api";
import { hitUrl, initials, repoShort, timeAgo } from "@/lib/format";
import { Avatar, RepoBadge } from "@/components/ui";

export function Timeline({
  repo,
  commits,
}: {
  repo: string;
  commits: EvidenceCommit[];
}) {
  return (
    <ol className="relative space-y-1 pl-1">
      <span className="absolute bottom-2 left-[13px] top-2 w-px bg-zinc-800" aria-hidden />
      {commits.map((ev) => {
        const introduced = ev.role === "introduced";
        const displayRepo = ev.pr_refs.length ? repo : repo;
        return (
          <li key={`${ev.sha}-${ev.role}`} className="relative flex gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-zinc-900/60">
            <span className="relative z-10 mt-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center">
              <span
                className={`flex h-full w-full items-center justify-center rounded-full border text-[10px] ${
                  introduced
                    ? "border-amber-500/50 bg-amber-500/15 text-amber-400"
                    : "border-zinc-800 bg-zinc-900 text-zinc-500"
                }`}
              >
                {introduced ? "★" : "·"}
              </span>
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <a
                  href={hitUrl({ sha: ev.sha, repo })}
                  target="_blank"
                  rel="noreferrer"
                  className={`font-mono text-xs underline-offset-2 hover:underline ${
                    introduced ? "text-amber-400" : "text-zinc-500"
                  }`}
                >
                  {ev.sha}
                </a>
                <span className="text-xs text-zinc-600">{timeAgo(ev.committed_at)}</span>
                <span className="flex items-center gap-1.5">
                  <Avatar label={initials(ev.author)} />
                  {ev.author && <span className="text-xs italic text-zinc-500">{ev.author}</span>}
                </span>
                {introduced && (
                  <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
                    introduced
                  </span>
                )}
                <RepoBadge repo={displayRepo} />
              </div>
              <p className={`mt-1 text-sm ${introduced ? "text-zinc-100" : "text-zinc-400"}`}>
                {ev.subject}
              </p>
              {ev.pr_refs.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {ev.pr_refs.map((n) => (
                    <a
                      key={n}
                      href={`https://github.com/${repo}/pull/${n}`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-violet-500/25 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[10px] text-violet-300 hover:border-violet-500/50"
                    >
                      #{n}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
