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
import { AbstentionBanner, AskView, WhyView } from "@/components/views";

type Mode = "auto" | "symbol" | "search";
type Result =
  | { kind: "why"; data: WhyResult }
  | { kind: "ask"; data: AskResult }
  | { kind: "answer"; data: AnswerResult; why?: WhyResult; ask?: AskResult }
  | null;

function looksLikeSymbol(input: string) {
  return /^[\w$]+(\.\w+)?$/.test(input.trim()) && input.trim().length > 1;
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

  async function run() {
    if (!repo || !query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const effectiveMode: Mode =
        mode === "auto" ? (looksLikeSymbol(query) ? "symbol" : "search") : mode;
      if (effectiveMode === "symbol") {
        const data = await why(repo, query.trim());
        setResult({ kind: "why", data });
      } else {
        const data = await ask(repo, query, 15);
        setResult({ kind: "ask", data });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAnswer() {
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
        askData = { query, abstained_reason: null, hits: data.hits, index_status: data.index_status };
      }
      setResult({ kind: "answer", data, why: whyData, ask: askData });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const current = repos.find((r) => r.name === repo);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        Codebase Archaeology
      </h1>
      <p className="mt-1 text-gray-600">
        Why does this code exist? Every claim traced to a commit or discussion.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <select
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          {repos.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name}
            </option>
          ))}
          {repos.length === 0 && <option>no indexed repos</option>}
        </select>
        {current && (
          <span className="text-xs text-gray-500">
            {current.commits?.toLocaleString()} commits ·{" "}
            {current.chunks?.toLocaleString()} chunks ·{" "}
            {current.complete_at_head ? "indexed at HEAD" : "partial index"}
          </span>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="createRoot   ·   why does the scheduler use lanes?"
          className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        <button
          onClick={run}
          disabled={busy || !query.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
        >
          {busy ? "…" : "Trace"}
        </button>
        <button
          onClick={runAnswer}
          disabled={busy || !query.trim()}
          title="requires OPENROUTER_API_KEY on the backend"
          className="rounded-md border border-blue-600 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-40"
        >
          Explain
        </button>
      </div>

      <div className="mt-2 flex gap-4 text-xs text-gray-500">
        {(["auto", "symbol", "search"] as Mode[]).map((m) => (
          <label key={m} className="flex items-center gap-1">
            <input
              type="radio"
              checked={mode === m}
              onChange={() => setMode(m)}
            />
            {m}
          </label>
        ))}
      </div>

      {error && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {result?.kind === "why" && (
        <section className="mt-8">
          <WhyView repo={repo} data={result.data} />
        </section>
      )}

      {result?.kind === "ask" && (
        <section className="mt-8">
          {result.data.abstained_reason && !result.data.hits.length ? (
            <AbstentionBanner reason={result.data.abstained_reason} />
          ) : (
            <AskView repo={repo} data={result.data} />
          )}
        </section>
      )}

      {result?.kind === "answer" && (
        <section className="mt-8 space-y-6">
          {result.data.status === "answered" && result.data.answer?.trim() ? (
            <article className="rounded-lg border border-gray-200 bg-white p-5 leading-relaxed whitespace-pre-wrap">
              {result.data.answer}
            </article>
          ) : (
            <AbstentionBanner reason={result.data.abstained_reason ?? "abstained"} />
          )}
          {(result.why || result.ask) && (
            <details>
              <summary className="cursor-pointer text-sm text-gray-500">
                underlying evidence {result.data.path === "A" ? "timeline" : "hits"}
              </summary>
              <div className="mt-3">
                {result.why && <WhyView repo={repo} data={result.why} />}
                {result.ask && <AskView repo={repo} data={result.ask} />}
              </div>
            </details>
          )}
        </section>
      )}
    </main>
  );
}
