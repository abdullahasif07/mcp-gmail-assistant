import Link from "next/link";
import { AlertCircle, Inbox, Sparkles, Send, ShieldCheck } from "lucide-react";
import SignInOptions from "@/components/SignInOptions";

const features = [
  {
    icon: Inbox,
    title: "Triage your inbox",
    body: "Read, search and skim recent unread mail in a clean Gmail-style layout.",
  },
  {
    icon: Sparkles,
    title: "AI suggested replies",
    body: "Gemini drafts a contextual reply you can edit in one click.",
  },
  {
    icon: Send,
    title: "Send from the app",
    body: "Compose or reply without ever leaving the assistant.",
  },
];

// Codes the backend sends back via /?auth_error=... when sign-in fails.
const AUTH_ERRORS: Record<string, string> = {
  access_denied: "Google sign-in was cancelled. Connect again whenever you're ready.",
  invalid_state: "The sign-in link expired or was tampered with. Please try again.",
};

export default async function Landing({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { auth_error } = await searchParams;
  const authError =
    typeof auth_error === "string"
      ? AUTH_ERRORS[auth_error] ?? `Google sign-in failed (${auth_error}). Please try again.`
      : null;

  return (
    <main className="flex flex-1 w-full flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-5xl">
        {authError && (
          <div
            role="alert"
            className="mx-auto mb-8 flex max-w-xl items-start gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-sm"
          >
            <AlertCircle className="h-4 w-4 shrink-0 translate-y-0.5 text-[var(--danger)]" />
            <span>{authError}</span>
          </div>
        )}
        <div className="flex flex-col items-center text-center gap-6">
          <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1 text-xs text-[var(--muted)]">
            <ShieldCheck className="h-3.5 w-3.5" />
            OAuth-secured · Gemini · MCP
          </span>
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight leading-tight">
            Your inbox, with an assistant.
          </h1>
          <p className="max-w-xl text-base sm:text-lg text-[var(--muted)]">
            Mailmind connects to Gmail through a local Model Context Protocol
            server and uses Gemini to read, summarise and reply to your email.
          </p>
          <div className="w-full max-w-3xl pt-4">
            <SignInOptions />
          </div>
          <p className="text-xs text-[var(--muted)]">
            Already signed in or in a demo?{" "}
            <Link href="/inbox" className="font-medium text-[var(--foreground)] underline-offset-4 hover:underline">
              Open the inbox
            </Link>
          </p>
        </div>

        <div className="mt-16 grid gap-4 sm:grid-cols-3">
          {features.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5"
            >
              <Icon className="h-5 w-5 text-[var(--accent)]" />
              <h3 className="mt-4 text-sm font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-[var(--muted)] leading-relaxed">
                {body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
