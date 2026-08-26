"use client";

import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SearchHit } from "@/lib/api";
import { hitUrl } from "@/lib/format";

function linkifyCitations(md: string, links: Record<string, string>): string {
  return md.replace(/\[([^\]\n]{2,60})\]/g, (match, inner: string) => {
    const url = links[inner.trim()];
    return url ? `[${inner}](${url})` : match;
  });
}

export function AnswerCard({
  answer,
  hits,
}: {
  answer: string;
  hits: SearchHit[];
}) {
  const [copied, setCopied] = useState(false);
  const links = useMemo(() => {
    const map: Record<string, string> = {};
    for (const h of hits) map[h.sha] = hitUrl(h);
    return map;
  }, [hits]);

  const processed = useMemo(() => linkifyCitations(answer, links), [answer, links]);

  async function copy() {
    await navigator.clipboard.writeText(answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article className="relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
      <button
        onClick={copy}
        className="absolute right-3 top-3 z-10 rounded-md border border-zinc-700/60 bg-zinc-900/90 px-2 py-1 text-[11px] text-zinc-400 transition-colors hover:border-zinc-600 hover:text-zinc-200"
      >
        {copied ? "copied" : "copy"}
      </button>
      <div className="answer-prose px-6 py-5">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: (p) => <h2 className="mb-3 mt-5 text-base font-semibold text-zinc-100 first:mt-0" {...p} />,
            h2: (p) => <h3 className="mb-2 mt-5 text-sm font-semibold uppercase tracking-wide text-amber-400/90 first:mt-0" {...p} />,
            h3: (p) => <h4 className="mb-2 mt-4 text-sm font-semibold text-zinc-200 first:mt-0" {...p} />,
            p: (p) => <p className="mb-3 leading-[1.75] text-zinc-300 last:mb-0" {...p} />,
            ul: (p) => <ul className="mb-3 space-y-1.5 pl-1 last:mb-0" {...p} />,
            ol: (p) => <ol className="mb-3 list-decimal space-y-1.5 pl-5 last:mb-0" {...p} />,
            li: (p) => <li className="leading-relaxed text-zinc-300 marker:text-zinc-600" {...p} />,
            strong: (p) => <strong className="font-semibold text-zinc-100" {...p} />,
            em: (p) => <em className="text-zinc-400" {...p} />,
            hr: () => <hr className="my-4 border-zinc-800" />,
            blockquote: (p) => (
              <blockquote className="mb-3 border-l-2 border-zinc-700 pl-3 text-zinc-400 last:mb-0" {...p} />
            ),
            code: (p) => (
              <code className="rounded bg-zinc-800/80 px-1 py-0.5 font-mono text-[12.5px] text-zinc-300" {...p} />
            ),
            pre: (p) => (
              <pre className="mb-3 overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-[12.5px] leading-relaxed last:mb-0" {...p} />
            ),
            a: (p) => <a className="text-blue-400 underline decoration-blue-400/30 underline-offset-2 hover:decoration-blue-400" target="_blank" rel="noreferrer" {...p} />,
          }}
        >
          {processed}
        </ReactMarkdown>
      </div>
    </article>
  );
}
