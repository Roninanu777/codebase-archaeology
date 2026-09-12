"use client";

import { useEffect, useState } from "react";
import { getSynthesisToken, TOKEN_STORAGE_KEY } from "@/lib/api";

export function SettingsButton() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setToken(getSynthesisToken());
  }, []);

  function save() {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
  }

  return (
    <span className="relative inline-flex">
      <button
        onClick={() => setOpen((o) => !o)}
        title="synthesis token settings"
        className="rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-xs text-zinc-400 transition-colors hover:border-zinc-600 hover:text-zinc-200"
      >
        token
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-72 rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-xl">
          <p className="text-[11px] text-zinc-400">
            Required for Explain and add-repo on hosted instances. Stored only in
            this browser.
          </p>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="X-Archaeology-Token"
            className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 font-mono text-xs text-zinc-100 focus:border-amber-500/60 focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between">
            <button
              onClick={() => {
                setToken("");
                window.localStorage.removeItem(TOKEN_STORAGE_KEY);
              }}
              className="text-[11px] text-zinc-500 hover:text-zinc-300"
            >
              clear
            </button>
            <button
              onClick={save}
              className="rounded-md bg-amber-500 px-3 py-1 text-xs font-semibold text-zinc-950 hover:bg-amber-400"
            >
              {saved ? "saved" : "save"}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
