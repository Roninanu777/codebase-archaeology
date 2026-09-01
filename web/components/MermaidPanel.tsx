"use client";

import { useEffect, useId, useState } from "react";

export function MermaidPanel({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const rawId = useId();
  const id = `mmd-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "strict",
        });
        const { svg: rendered } = await mermaid.render(id, code);
        if (!cancelled) setSvg(rendered);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (failed || !svg) return null;
  return (
    <details className="group rounded-xl border border-zinc-800 bg-zinc-900/40">
      <summary className="cursor-pointer select-none px-4 py-2.5 text-xs uppercase tracking-wider text-zinc-500 transition-colors hover:text-zinc-300">
        concept map
      </summary>
      <div
        className="flex justify-center overflow-x-auto px-4 pb-4 [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </details>
  );
}
