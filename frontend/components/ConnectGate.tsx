"use client";

import SignInOptions from "@/components/SignInOptions";

export default function ConnectGate() {
  return (
    <main className="flex flex-1 w-full flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-3xl text-center">
        <h1 className="text-xl font-semibold tracking-tight">
          Choose how to explore Mailmind
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Pick how you&apos;d like to get in.
        </p>
        <div className="mt-8">
          <SignInOptions />
        </div>
      </div>
    </main>
  );
}
