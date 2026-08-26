"use client";

import type { AskResult, EvidenceCommit, WhyResult } from "@/lib/api";

const GITHUB_COMMIT = (repo: string, sha: string) =>
  `https://github.com/${repo}/commit/${sha.replace(/^pr:/, "")}`;
const GITHUB_PR = (repo: string, n: number) =>
  `https://github.com/${repo}/pull/${n}`;

function isPrId(sha: string) {
  return sha.startsWith("pr:");
}

function CommitLink({
  repo,
  sha,
  children,
}: {
  repo: string;
  sha: string;
  children: React.ReactNode;
}) {
  if (isPrId(sha)) {
    const num = parseInt(sha.slice(3), 10);
    return (
      <a
        href={GITHUB_PR(repo, num)}
        target="_blank"
        rel="noreferrer"
        className="font-mono text-blue-600 hover:underline"
      >
        {children}
      </a>
    );
  }
  return (
    <a
      href={GITHUB_COMMIT(repo, sha)}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-blue-600 hover:underline"
    >
      {children}
    </a>
  );
}

function TimelineRow({ repo, ev }: { repo: string; ev: EvidenceCommit }) {
  const introduced = ev.role === "introduced";
  return (
    <li className="flex gap-3 py-2 border-b border-gray-100 last:border-0">
      <span className={`mt-1 ${introduced ? "text-amber-500" : "text-gray-300"}`}>
        {introduced ? "\u2605" : "\u2022"}
      </span>
      <div>
        <CommitLink repo={repo} sha={ev.sha}>
          {ev.sha.slice(0, 9)}
        </CommitLink>
        <span className="ml-2 text-sm text-gray-500">{ev.committed_at}</span>
        {ev.author && <span className="ml-2 text-sm italic">{ev.author}</span>}
        {ev.pr_refs.map((n) => (
          <a
            key={n}
            href={GITHUB_PR(repo, n)}
            target="_blank"
            rel="noreferrer"
            className="ml-2 text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded hover:bg-blue-100"
          >
            #{n}
          </a>
        ))}
        <p className={introduced ? "font-medium" : ""}>{ev.subject}</p>
      </div>
    </li>
  );
}

export function WhyView({ repo, data }: { repo: string; data: WhyResult }) {
  if (data.status === "abstained") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="font-medium text-amber-800">No reliable answer</p>
        <p className="text-sm text-amber-700">{data.reason}</p>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-2 text-sm text-gray-600">
        <span className="font-mono">{data.symbol}</span>{" "}
        @ <span className="font-mono">{data.rel_path}</span>
        {data.span && (
          <span className="font-mono">
            :{data.span.start_line}-{data.span.end_line}
          </span>
        )}
        <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs">
          {data.noise_dropped} noise dropped
        </span>
      </div>
      <ul>
        {[...(data.timeline ?? [])].reverse().map((ev) => (
          <TimelineRow key={`${ev.sha}-${ev.role}`} repo={repo} ev={ev} />
        ))}
      </ul>
    </div>
  );
}

export function AskView({ repo, data }: { repo: string; data: AskResult }) {
  if (!data.hits?.length) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm text-amber-700">{data.abstained_reason}</p>
      </div>
    );
  }
  return (
    <ol className="space-y-2">
      {data.hits.map((h, i) => (
        <li key={`${h.sha}-${i}`} className="flex items-baseline gap-3 py-1">
          <span className="w-6 text-right text-gray-400">{i + 1}.</span>
          <CommitLink repo={repo} sha={h.sha}>
            {h.sha}
          </CommitLink>
          {h.authored_at && (
            <span className="text-sm text-gray-500">{h.authored_at}</span>
          )}
          {h.stale && (
            <span className="rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-700">
              STALE {Math.round((h.liveness_score ?? 0) * 100)}%
            </span>
          )}
          <span className="truncate">{h.title}</span>
        </li>
      ))}
    </ol>
  );
}

export function AbstentionBanner({ reason }: { reason: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
      {reason}
    </div>
  );
}
