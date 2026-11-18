"use client";

import { ShieldCheck } from "lucide-react";
import SignInOptions from "@/components/SignInOptions";

export default function ConnectGate() {
  return (
    <main className="flex flex-1 w-full flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-3xl text-center">
        <h1 className="text-xl font-semibold tracking-tight">
          Choose how to explore Mailmind
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Jump into the demo inbox, or connect your own Gmail account.
        </p>
        <div className="mt-8">
          <SignInOptions />
        </div>
        <p className="mt-6 inline-flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
          <ShieldCheck className="h-3 w-3" />
          Gmail access uses Google OAuth. We never see your password, and your
          token is stored encrypted.
        </p>
      </div>
    </main>
  );
}
