"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  RotateCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import {
  clearChatHistory,
  discardChatDraft,
  getChatHistory,
  type ChatMessage,
  type ChatResult,
  type PendingAction,
} from "@/lib/api";

type Props = {
  onSend: (message: string) => Promise<ChatResult>;
  onConfirm: (action: PendingAction) => Promise<string>;
  /** Called after an email was sent from chat, so the inbox can refresh. */
  onMailChanged?: () => void;
};

function summariseArgs(args: Record<string, unknown>): {
  to?: string;
  subject?: string;
  body?: string;
} {
  return {
    to: typeof args.to === "string" ? args.to : undefined,
    subject: typeof args.subject === "string" ? args.subject : undefined,
    body: typeof args.body === "string" ? args.body : undefined,
  };
}

export default function ChatBar({ onSend, onConfirm, onMailChanged }: Props) {
  const [value, setValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  // Restore the conversation the backend remembers (survives reloads).
  useEffect(() => {
    getChatHistory()
      .then((h) => {
        setMessages(h.messages);
        setPending(h.pendingAction);
      })
      .catch(() => {
        // No history is fine; the chat still works.
      });
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending, loading, collapsed]);

  const say = (role: ChatMessage["role"], text: string) =>
    setMessages((prev) => [...prev, { role, text }]);

  async function submit() {
    const msg = value.trim();
    if (!msg || loading) return;
    setLoading(true);
    setError(null);
    setPending(null);
    setCollapsed(false);
    say("user", msg);
    setValue("");
    try {
      const res = await onSend(msg);
      say("assistant", res.reply);
      setPending(res.pendingAction ?? null);
      if (res.sent) onMailChanged?.();
    } catch (e) {
      setError((e as Error).message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function confirmAction() {
    if (!pending || confirming) return;
    setConfirming(true);
    setError(null);
    try {
      say("assistant", await onConfirm(pending));
      setPending(null);
    } catch (e) {
      setError((e as Error).message || "Confirm failed");
    } finally {
      setConfirming(false);
    }
  }

  function cancelAction() {
    setPending(null);
    say("assistant", "Draft discarded.");
    // Make the backend forget it too, so a later "yes" can't send it.
    discardChatDraft().catch(() => {});
  }

  async function newChat() {
    setMessages([]);
    setPending(null);
    setError(null);
    await clearChatHistory().catch(() => {});
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const summary = pending ? summariseArgs(pending.args) : null;
  const hasThread = messages.length > 0 || pending || error || loading;

  return (
    <div className="border-t border-[var(--border)] bg-[var(--surface)] px-4 py-3">
      {hasThread && (
        <div className="mx-auto mb-2 max-w-3xl">
          <div className="mb-1.5 flex items-center justify-between text-[11px] text-[var(--muted)]">
            <span className="inline-flex items-center gap-1.5 font-medium uppercase tracking-wide">
              <Sparkles className="h-3 w-3 text-[var(--accent)]" />
              Assistant
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={newChat}
                disabled={loading}
                className="inline-flex h-6 items-center gap-1 rounded-md px-2 transition hover:bg-[var(--surface-muted)] hover:text-[var(--foreground)] disabled:opacity-50"
                title="Clear the conversation and start over"
              >
                <RotateCcw className="h-3 w-3" />
                New chat
              </button>
              <button
                onClick={() => setCollapsed((c) => !c)}
                className="inline-flex h-6 w-6 items-center justify-center rounded-md transition hover:bg-[var(--surface-muted)] hover:text-[var(--foreground)]"
                aria-label={collapsed ? "Show conversation" : "Hide conversation"}
              >
                {collapsed ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

          {!collapsed && (
            <div
              ref={threadRef}
              className="max-h-[38vh] space-y-2 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3"
            >
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
                        : "border border-[var(--border)] bg-[var(--surface)]"
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Thinking…
                </div>
              )}

              {error && (
                <div className="text-xs text-[var(--danger)]">{error}</div>
              )}

              {pending && summary && (
                <div className="rounded-xl border border-[var(--border-strong)] bg-[var(--surface)] p-3 text-sm shadow-sm">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                    <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />
                    Draft ready — click Confirm or reply “yes”
                  </div>
                  <dl className="mt-2 space-y-1.5">
                    {summary.to && <Row label="To" value={summary.to} />}
                    {summary.subject && <Row label="Subject" value={summary.subject} />}
                    {summary.body && (
                      <div>
                        <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--muted)]">
                          Body
                        </div>
                        <pre className="whitespace-pre-wrap break-words rounded-lg bg-[var(--surface-muted)] p-2 font-sans text-sm leading-relaxed">
                          {summary.body}
                        </pre>
                      </div>
                    )}
                  </dl>
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={confirmAction}
                      disabled={confirming}
                      className="btn-accent inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-xs font-medium disabled:opacity-60"
                    >
                      {confirming ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      )}
                      Confirm & send
                    </button>
                    <button
                      onClick={cancelAction}
                      disabled={confirming}
                      className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[var(--border-strong)] px-4 text-xs font-medium transition hover:bg-[var(--surface-muted)] disabled:opacity-60"
                    >
                      <X className="h-3.5 w-3.5" />
                      Discard
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-full border border-[var(--border-strong)] bg-[var(--surface-muted)] px-3 py-1.5">
        <Sparkles className="h-4 w-4 shrink-0 text-[var(--accent)]" />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={loading}
          placeholder={
            pending
              ? "Reply “yes” to send, or ask for changes…"
              : "Ask anything — e.g. “summarise my unread mail” or “reply to Marcus that we’re on track”"
          }
          className="flex-1 border-0 bg-transparent text-sm outline-none placeholder:text-[var(--muted)] disabled:opacity-70"
        />
        <button
          onClick={submit}
          disabled={loading || !value.trim()}
          className="btn-accent inline-flex h-8 w-8 items-center justify-center rounded-full disabled:opacity-50"
          aria-label="Send"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <dt className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-[var(--muted)] pt-0.5">
        {label}
      </dt>
      <dd className="flex-1 break-words text-sm">{value}</dd>
    </div>
  );
}
