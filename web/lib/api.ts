export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "archaeology_token";

export function getSynthesisToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
}

function gatedHeaders(): Record<string, string> {
  const token = getSynthesisToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-Archaeology-Token"] = token;
  return headers;
}

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
  repo?: string | null;
}

export interface AskResult {
  query: string;
  abstained_reason: string | null;
  hits: SearchHit[];
  index_status: IndexStatus | null;
}

export interface AnswerResult {
  path: "A" | "B";
  query: string;
  status: string;
  answer: string | null;
  abstained_reason: string | null;
  citations: string[];
  model: string | null;
  mermaid?: string | null;
  hits?: SearchHit[] | null;
  index_status: IndexStatus | null;
}

export function answerRouted(repo: string, query: string): Promise<AnswerResult> {
  return fetch(`${API_BASE}/repos/${encodeURIComponent(repo)}/answer`, {
    method: "POST",
    headers: gatedHeaders(),
    body: JSON.stringify({ query }),
  }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `API ${res.status}`);
    }
    return res.json() as Promise<AnswerResult>;
  });
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

export function indexRemote(
  repo: string
): Promise<{ job_id: number; run_key: string; status: string }> {
  return fetch(`${API_BASE}/repos/index-remote`, {
    method: "POST",
    headers: gatedHeaders(),
    body: JSON.stringify({ repo }),
  }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `API ${res.status}`);
    }
    return res.json();
  });
}

export interface JobStatus {
  job_id: number;
  run_key: string;
  status: string;
  stage?: string | null;
  detail?: string | null;
  error?: string | null;
}

export function jobStatus(jobId: number): Promise<JobStatus> {
  return getJson<JobStatus>(`/jobs/${jobId}`);
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
