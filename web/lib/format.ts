export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.floor((Date.now() - then) / 1000);
  const units: [number, string][] = [
    [60, "s"],
    [3600, "m"],
    [86400, "h"],
    [86400 * 30, "d"],
    [86400 * 365, "mo"],
  ];
  if (seconds < 60) return "now";
  for (let i = 1; i < units.length; i++) {
    if (seconds < units[i][0]) {
      const divisor = units[i - 1][0];
      return `${Math.floor(seconds / divisor)}${units[i][1]}`;
    }
  }
  const years = Math.floor(seconds / (86400 * 365));
  return `${years}y`;
}

export function shortDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function repoShort(name: string | null | undefined): string {
  if (!name) return "";
  const parts = name.split("/");
  return parts[parts.length - 1];
}

export function initials(name: string | null | undefined): string {
  if (!name) return "·";
  const parts = name.trim().split(/[\s_.@-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export function hitUrl(hit: { sha: string; repo?: string | null }): string {
  const repo = hit.repo || "";
  if (hit.sha.startsWith("pr:")) {
    return `https://github.com/${repo}/pull/${hit.sha.slice(3)}`;
  }
  if (hit.sha.includes("/")) {
    const path = hit.sha.split("#")[0];
    return `https://github.com/${repo}/blob/HEAD/${path}`;
  }
  return `https://github.com/${repo}/commit/${hit.sha}`;
}
