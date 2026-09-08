"use client";

import { useEffect, useRef, useState } from "react";
import {
  indexRemote,
  jobStatus,
  listRepos,
  type IndexStatus,
  type JobStatus,
} from "@/lib/api";

const STAGES = ["cloning", "commits", "significance", "prs", "embedding"];

export function AddRepoFlow({ onAdded }: { onAdded: (repos: IndexStatus[]) => void }) {
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [job, setJob] = useState<number | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  function stop() {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }

  function poll(id: number) {
    jobStatus(id)
      .then((s) => {
        setStatus(s);
        if (s.status === "done") {
          stop();
          listRepos().then((rs) => {
            onAdded(rs);
            setTimeout(() => {
              setOpen(false);
              setStatus(null);
              setJob(null);
            }, 1200);
          });
        }
        if (s.status === "failed") stop();
      })
      .catch(() => undefined);
  }

  function start() {
    const clean = slug.trim();
    const slugLike = /^[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*$/.test(clean);
    const urlLike = /github\.com\//i.test(clean);
    if (!slugLike && !urlLike) {
      setError("paste a GitHub URL or owner/repo");
      return;
    }
    setError(null);
    indexRemote(clean)
      .then((h) => {
        setJob(h.job_id);
        setStatus({ job_id: h.job_id, run_key: h.run_key, status: "pending", stage: "cloning" });
        stop();
        timer.current = setInterval(() => poll(h.job_id), 2000);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  const stageIdx = status?.stage ? STAGES.indexOf(status.stage) : -1;

  return (
    <span className="relative inline-flex">
      <button
        onClick={() => setOpen((o) => !o)}
        title="index a public GitHub repo"
        className="rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-xs text-zinc-400 transition-colors hover:border-amber-500/50 hover:text-amber-400"
      >
        + add
      </button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-80 rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl">
          {!status ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                start();
              }}
            >
              <input
                autoFocus
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 font-mono text-xs text-zinc-100 focus:border-amber-500/60 focus:outline-none"
              />
              <div className="mt-2 flex items-center justify-between">
                <span className="text-[10px] text-zinc-600">paste a GitHub URL or owner/repo</span>
                <button
                  type="submit"
                  disabled={!slug.trim()}
                  className="rounded-md bg-amber-500 px-3 py-1 text-xs font-semibold text-zinc-950 hover:bg-amber-400 disabled:opacity-40"
                >
                  index
                </button>
              </div>
            </form>
          ) : (
            <div>
              <p className="font-mono text-[11px] text-zinc-300">{slug}</p>
              <div className="mt-2 space-y-1">
                {STAGES.map((s, i) => {
                  const active = status.stage === s && status.status !== "failed";
                  const done =
                    status.status === "done" || (stageIdx >= 0 && i < stageIdx && status.status !== "failed");
                  return (
                    <div key={s} className="flex items-center gap-2 text-[11px]">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          done
                            ? "bg-emerald-400"
                            : active
                              ? "animate-pulse bg-amber-400"
                              : status.status === "failed" && status.stage === s
                                ? "bg-red-400"
                                : "bg-zinc-700"
                        }`}
                      />
                      <span
                        className={
                          active
                            ? "text-amber-400"
                            : done
                              ? "text-zinc-400"
                              : status.status === "failed" && status.stage === s
                                ? "text-red-400"
                                : "text-zinc-600"
                        }
                      >
                        {s}
                      </span>
                      {active && status.detail && (
                        <span className="truncate font-mono text-[10px] text-zinc-600">
                          {status.detail}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
              {status.status === "failed" && (
                <p className="mt-2 font-mono text-[10px] text-red-400">{status.error}</p>
              )}
              {status.status === "done" && (
                <p className="mt-2 text-[11px] text-emerald-400">indexed ✓</p>
              )}
              <button
                onClick={() => {
                  stop();
                  setOpen(false);
                  setStatus(null);
                  setJob(null);
                  setSlug("");
                }}
                className="mt-2 w-full rounded-md border border-zinc-700 px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-300"
              >
                {status.status === "done" ? "close" : "dismiss (keeps running)"}
              </button>
            </div>
          )}
          {error && <p className="mt-2 font-mono text-[10px] text-red-400">{error}</p>}
        </div>
      )}
    </span>
  );
}
