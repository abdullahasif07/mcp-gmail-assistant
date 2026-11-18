/** Display helpers for RFC 5322 "From" headers like `"Alice B" <a@b.com>`. */

export function displayName(from: string): string {
  const m = from.match(/^(.*?)\s*<(.*?)>$/);
  if (!m) return from;
  return m[1].replace(/"/g, "").trim() || m[2];
}

export function senderEmail(from: string): string {
  return from.match(/<(.*?)>/)?.[1] ?? from;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}
