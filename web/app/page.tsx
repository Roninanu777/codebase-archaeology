"use client";

import { useEffect, useState } from "react";
import {
  answerRouted,
  ask,
  listRepos,
  why,
  type AnswerResult,
  type AskResult,
  type IndexStatus,
  type WhyResult,
} from "@/lib/api";
import { AnswerCard } from "@/components/AnswerCard";
import { EvidenceArc, type ArcPoint } from "@/components/Diagram";
import { HitList } from "@/components/HitList";
import { MermaidPanel } from "@/components/MermaidPanel";
import { QueryBar, type Mode } from "@/components/QueryBar";
import { Timeline } from "@/components/Timeline";
import { ErrorPanel, InfoPanel, Skeleton } from "@/components/ui";

type Result =
  | { kind: "why"; data: WhyResult }
  | { kind: "ask"; data: AskResult }
  | {
      kind: "answer";
      data: AnswerResult;
      why?: WhyResult;
      ask?: AskResult;
    }
  | null;

function looksLikeSymbol(input: string) {
  return /^[\w$]+(\.\w+)?$/.test(input.trim()) && input.trim().length > 1;
}

function SectionHeader({ label, count }: { label: string; count?: number }) {
  return (
    <div className="mb-2 flex items-baseline gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
        {label}
      </h2>
      {count !== undefined && (
        <span className="font-mono text-[11px] text-zinc-600">{count}</span>
      )}
    </div>
  );
}

export default function Home() {
  const [repos, setRepos] = useState<IndexStatus[]>([]);
  const [repo, setRepo] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [result, setResult] = useState<Result>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listRepos()
      .then((rs) => {
        setRepos(rs);
        if (rs.length > 0) setRepo(rs[0].name);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function runTrace() {
    if (!repo || !query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const effective: Mode =
        mode === "auto" ? (looksLikeSymbol(query) ? "symbol" : "search") : mode;
      if (effective === "symbol") {
        setResult({ kind: "why", data: await why(repo, query.trim()) });
      } else {
        setResult({ kind: "ask", data: await ask(repo, query, 15) });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runExplain() {
    if (!repo || !query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await answerRouted(repo, query.trim());
      let whyData: WhyResult | undefined;
      let askData: AskResult | undefined;
      if (data.path === "A") {
        whyData = await why(repo, query.trim());
      } else if (data.hits?.length) {
        askData = {
          query,
          abstained_reason: null,
          hits: data.hits,
          index_status: data.index_status,
        };
      }
      setResult({ kind: "answer", data, why: whyData, ask: askData });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const totals = repos.reduce(
    (acc, r) => ({
      commits: acc.commits + (r.commits ?? 0),
      chunks: acc.chunks + (r.chunks ?? 0),
    }),
    { commits: 0, chunks: 0 }
  );

  let answerArc: ArcPoint[] | null = null;
  if (result?.kind === "answer") {
    if (result.data.path === "A" && result.why) {
      answerArc = result.why.timeline.map((ev) => ({
        date: ev.committed_at,
        title: ev.subject,
        sub: ev.author ?? undefined,
        kind: ev.role === "introduced" ? "introduced" : "modified",
      }));
    } else if (result.data.hits?.length) {
      answerArc = result.data.hits.map((h) => ({
        date: h.authored_at,
        title: h.title,
        kind: "hit" as const,
        liveness: h.liveness_score,
        repo: h.repo,
      }));
    }
    if (answerArc && answerArc.length < 3) answerArc = null;
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-6 pb-12">
      <header className="flex items-center gap-3 pb-4 pt-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900">
          <svg viewBox="0 0 32 32" className="h-5 w-5">
            <rect x="7" y="20" width="18" height="3" rx="1.5" fill="#52525b" />
            <rect x="7" y="14.5" width="13" height="3" rx="1.5" fill="#a1a1aa" />
            <rect x="7" y="9" width="8" height="3" rx="1.5" fill="#f59e0b" />
            <circle cx="23" cy="10.5" r="3.5" fill="none" stroke="#f59e0b" strokeWidth="2" />
            <path d="M25.5 13 L28.5 16" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
        <div>
          <h1 className="text-[15px] font-semibold tracking-tight text-zinc-100">
            Codebase Archaeology
          </h1>
          <p className="text-[11px] text-zinc-500">
            Why does this code exist? Every claim traced to a commit or discussion.
          </p>
        </div>
      </header>

      <QueryBar
        repos={repos}
        repo={repo}
        onRepoChange={setRepo}
        query={query}
        onQueryChange={setQuery}
        mode={mode}
        onModeChange={setMode}
        busy={busy}
        onTrace={runTrace}
        onExplain={runExplain}
      />

      {error && (
        <div className="mt-5">
          <ErrorPanel message={error} />
        </div>
      )}

      {busy && !result && (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-4/5" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {result?.kind === "why" && (
        <section className="mt-5">
          {result.data.status === "abstained" ? (
            <InfoPanel title="No reliable answer">
              <span className="font-mono text-xs">{result.data.reason}</span>
              <p className="mt-2">
                Symbol anchoring needs a validated language. Try the search mode
                for prose questions.
              </p>
            </InfoPanel>
          ) : (
            <>
              <SectionHeader label="Timeline" count={result.data.timeline.length} />
              <Timeline repo={repo} commits={result.data.timeline} />
            </>
          )}
        </section>
      )}

      {result?.kind === "ask" && (
        <section className="mt-5">
          {!result.data.hits?.length ? (
            <InfoPanel title="Nothing retrieved">
              {result.data.abstained_reason ?? "the index has no matching evidence"}
            </InfoPanel>
          ) : (
            <>
              <SectionHeader label="Evidence hits" count={result.data.hits.length} />
              <HitList hits={result.data.hits} />
            </>
          )}
        </section>
      )}

      {result?.kind === "answer" && (
        <section className="mt-5 space-y-4">
          {result.data.status === "answered" && result.data.answer?.trim() ? (
            <>
              <div className="flex items-center gap-2 text-[11px] text-zinc-600">
                <span className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono">
                  {result.data.model}
                </span>
                <span>path {result.data.path}</span>
                {result.data.citations.length > 0 && (
                  <span>· {result.data.citations.length} citations resolved</span>
                )}
              </div>
              <AnswerCard
                answer={result.data.answer}
                hits={result.data.hits ?? []}
                mermaid={result.data.mermaid}
              />
              {answerArc && (
                <>
                  <SectionHeader label="Arc" />
                  <EvidenceArc points={answerArc} />
                </>
              )}
            </>
          ) : (
            <InfoPanel title="Abstained">
              <span className="font-mono text-xs">
                {result.data.abstained_reason ?? "no answer"}
              </span>
              <p className="mt-2">
                The model declined to answer beyond the evidence — that is the
                intended behavior, not a failure.
              </p>
            </InfoPanel>
          )}
          {(result.why || result.ask) && (
            <details className="group">
              <summary className="cursor-pointer select-none text-xs uppercase tracking-wider text-zinc-600 transition-colors hover:text-zinc-400">
                ▸ underlying evidence {result.data.path === "A" ? "timeline" : "hits"}
              </summary>
              <div className="mt-3">
                {result.why && (
                  <>
                    <SectionHeader label="Timeline" count={result.why.timeline.length} />
                    <Timeline repo={repo} commits={result.why.timeline} />
                  </>
                )}
                {result.ask && (
                  <>
                    <SectionHeader label="Hits" count={result.ask.hits.length} />
                    <HitList hits={result.ask.hits} />
                  </>
                )}
              </div>
            </details>
          )}
        </section>
      )}

      {!result && !busy && !error && (
        <div className="mt-8 rounded-xl border border-dashed border-zinc-800 p-8 text-center">
          <p className="text-sm text-zinc-500">
            Pick a repo, type a symbol or a question, then Trace.
          </p>
          <p className="mt-1 text-xs text-zinc-600">
            Explain adds LLM synthesis with mandatory citations and an arc diagram.
          </p>
        </div>
      )}

      <footer className="mt-12 border-t border-zinc-800/70 pt-3 text-[11px] text-zinc-600">
        {repos.length > 0 && (
          <span>
            {repos.length} repos · {totals.commits.toLocaleString()} commits ·{" "}
            {totals.chunks.toLocaleString()} chunks indexed
          </span>
        )}
        <span className="float-right">every claim carries a sha</span>
      </footer>
    </main>
  );
}
