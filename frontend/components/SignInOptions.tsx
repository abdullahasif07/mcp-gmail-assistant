"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical, KeyRound, Loader2, Mail } from "lucide-react";
import {
  ApiError,
  AUTH_LOGIN_URL,
  getDemoInfo,
  startDemo,
  type DemoInfo,
} from "@/lib/api";

/**
 * The two ways into the app:
 *   1. Recruiter demo — a sandboxed, pre-seeded fake inbox. No Google account.
 *   2. Real Gmail    — Google OAuth (limited to approved test users while the
 *                      Google Cloud app is in testing mode).
 */
export default function SignInOptions() {
  const router = useRouter();
  const [info, setInfo] = useState<DemoInfo | null>(null);
  const [code, setCode] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDemoInfo()
      .then(setInfo)
      // Backend unreachable: keep the button; the click will surface the error.
      .catch(() => setInfo({ enabled: true, accessCodeRequired: false }));
  }, []);

  async function onStartDemo(e: FormEvent) {
    e.preventDefault();
    setStarting(true);
    setError(null);
    try {
      await startDemo(code.trim() || undefined);
      router.push("/inbox");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Can't reach the backend right now. Please try again shortly."
      );
      setStarting(false);
    }
  }

  const demoEnabled = info?.enabled ?? true;
  const needsCode = info?.accessCodeRequired ?? false;

  return (
    <div className="grid w-full gap-4 text-left sm:grid-cols-2">
      {demoEnabled && (
        <form
          onSubmit={onStartDemo}
          className="flex flex-col rounded-2xl border border-[var(--accent)]/40 bg-[var(--surface)] p-6"
        >
          <div className="flex items-center justify-between gap-2">
            <FlaskConical className="h-5 w-5 text-[var(--accent)]" />
            <span className="rounded-full bg-[var(--surface-muted)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--accent)]">
              For recruiters
            </span>
          </div>
          <h2 className="mt-4 text-base font-semibold">Try the demo inbox</h2>
          <p className="mt-1.5 flex-1 text-sm leading-relaxed text-[var(--muted)]">
            A <span className="text-[var(--foreground)]">dummy email account</span>{" "}
            pre-filled with fictional emails. No Google sign-in needed. AI replies,
            the chat assistant, search and filters all work, and anything you
            &quot;send&quot; just lands in the demo&apos;s Sent folder.
          </p>

          {needsCode && (
            <div className="relative mt-4">
              <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted)]" />
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Access code"
                aria-label="Demo access code"
                autoComplete="off"
                className="h-10 w-full rounded-lg pl-9 pr-3 text-sm outline-none"
              />
            </div>
          )}

          {error && (
            <p role="alert" className="mt-3 text-xs text-[var(--danger)]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={starting || (needsCode && !code.trim())}
            className="btn-accent mt-4 inline-flex h-10 items-center justify-center gap-2 rounded-full text-sm font-medium disabled:opacity-60"
          >
            {starting && <Loader2 className="h-4 w-4 animate-spin" />}
            Start demo
          </button>
        </form>
      )}

      <div
        className={`flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 ${
          demoEnabled ? "" : "sm:col-span-2"
        }`}
      >
        <Mail className="h-5 w-5 text-[var(--accent)]" />
        <h2 className="mt-4 text-base font-semibold">Use your own Gmail</h2>
        <p className="mt-1.5 flex-1 text-sm leading-relaxed text-[var(--muted)]">
          Connect a real Gmail account with Google OAuth to read, search and
          reply to your actual mail. While the app is in Google&apos;s testing
          mode, only approved accounts can sign in.
        </p>
        <a
          href={AUTH_LOGIN_URL}
          className="mt-4 inline-flex h-10 items-center justify-center rounded-full border border-[var(--border-strong)] text-sm font-medium transition hover:bg-[var(--surface-muted)]"
        >
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
