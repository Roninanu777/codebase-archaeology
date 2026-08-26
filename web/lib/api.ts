export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface IndexStatus {
  name: string;
  head_sha?: string | null;
  indexed_through_sha?: string | null;
  commits?: number;
  significance?: Record<string, number>;
  chunks?: number;
  embedded_chunks?: number;
  complete_at_head?: boolean;
}

export interface EvidenceCommit {
  sha: string;
  role: string;
  subject: string;
  author: string | null;
  committed_at: string | null;
  pr_refs: number[];
}

export interface Span {
  start_line: number;
  end_line: number;
  kind: string;
}

export interface WhyResult {
  status: string;
  reason: string | null;
  symbol: string;
  rel_path: string | null;
  span: Span | null;
  introduced: EvidenceCommit | null;
  timeline: EvidenceCommit[];
  noise_dropped: number;
  cache_hit: boolean;
  index_status: IndexStatus | null;
}

export interface SearchHit {
  sha: string;
  title: string;
  authored_at: string | null;
  dense_rank: number | null;
  sparse_rank: number | null;
  liveness_score: number | null;
  rerank_score?: number | null;
  stale: boolean;
}

export interface AskResult {
  query: string;
  abstained_reason: string | null;
  hits: SearchHit[];
  index_status: IndexStatus | null;
}

export interface AnswerResult {
  status: string;
  symbol: string;
  answer: string | null;
  abstained_reason: string | null;
  citations: string[];
  model: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function listRepos(): Promise<IndexStatus[]> {
  return getJson<IndexStatus[]>("/repos");
}

export function why(repo: string, symbol: string): Promise<WhyResult> {
  return getJson<WhyResult>(
    `/repos/${encodeURIComponent(repo)}/why/${encodeURIComponent(symbol)}`
  );
}

export function ask(repo: string, q: string, n = 10): Promise<AskResult> {
  return getJson<AskResult>(
    `/repos/${encodeURIComponent(repo)}/ask?q=${encodeURIComponent(q)}&n=${n}`
  );
}

export function answer(
  repo: string,
  symbol: string,
  file: string | null
): Promise<AnswerResult> {
  const fileParam = file ? `&file=${encodeURIComponent(file)}` : "";
  return getJson<AnswerResult>(
    `/repos/${encodeURIComponent(repo)}/answer/${encodeURIComponent(symbol)}?1=1${fileParam}`
  );
}
