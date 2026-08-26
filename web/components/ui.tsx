"use client";

import type { ReactNode } from "react";
import { repoShort } from "@/lib/format";

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function RepoBadge({ repo }: { repo?: string | null }) {
  if (!repo) return null;
  return (
    <span className="inline-flex items-center rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
      {repoShort(repo)}
    </span>
  );
}

export function LivenessChip({ score, stale }: { score: number | null; stale: boolean }) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  const tone = stale
    ? "border-orange-500/30 bg-orange-500/10 text-orange-400"
    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${tone}`}>
      {pct}% alive
    </span>
  );
}

export function TypeIcon({ sha }: { sha: string }) {
  if (sha.startsWith("pr:")) {
    return (
      <svg className="h-3.5 w-3.5 shrink-0 text-violet-400" viewBox="0 0 16 16" fill="currentColor">
        <path d="M5 3.25a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0ZM3.75 6v4.3a2.25 2.25 0 1 0 1.5 0V6a2.25 2.25 0 1 0-1.5 0v.25Zm.5 6.75a.75.75 0 1 1 0 1.5.75.75 0 0 1 0-1.5Zm6-9a1.25 1.25 0 1 0 0 .5v.5c0 .966-.784 1.75-1.75 1.75H7v3.7a2.25 2.25 0 1 0 1.5 0V7.5h.25A3.25 3.25 0 0 0 12 4.25v-.5a1.25 1.25 0 0 0-.5-2.5Z" />
      </svg>
    );
  }
  if (sha.includes("/")) {
    return (
      <svg className="h-3.5 w-3.5 shrink-0 text-sky-400" viewBox="0 0 16 16" fill="currentColor">
        <path d="M4 1.75A1.75 1.75 0 0 1 5.75 0h5.5a.75.75 0 0 1 .53.22l3 3a.75.75 0 0 1 .22.53v8.5A1.75 1.75 0 0 1 13.25 14h-7.5A1.75 1.75 0 0 1 4 12.25Zm-2 3c0-.09.007-.178.02-.265L2.005 13A1.75 1.75 0 0 0 3.75 15h6.5v-1.5h-6.5a.25.25 0 0 1-.25-.25Z" />
      </svg>
    );
  }
  return (
    <svg className="h-3.5 w-3.5 shrink-0 text-zinc-500" viewBox="0 0 16 16" fill="currentColor">
      <circle cx="8" cy="8" r="3.5" />
    </svg>
  );
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
            value === opt.value
              ? "bg-zinc-700/80 text-zinc-100"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function InfoPanel({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
      {title && <p className="mb-1 font-medium text-zinc-200">{title}</p>}
      <div className="text-sm leading-relaxed text-zinc-400">{children}</div>
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-500/25 bg-red-500/5 p-5">
      <p className="font-mono text-sm text-red-400">{message}</p>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-zinc-800/70 ${className}`} />;
}

export function Avatar({ label }: { label: string }) {
  return (
    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-800 font-mono text-[9px] text-zinc-400">
      {label}
    </span>
  );
}
