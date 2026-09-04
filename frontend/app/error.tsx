"use client";

import { useEffect } from "react";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="fatal-error">
      <p>F1 VIRTUAL PIT WALL</p>
      <h1>The dashboard could not render.</h1>
      <span>{error.message || "An unexpected interface error occurred."}</span>
      <button onClick={reset}>TRY AGAIN</button>
    </main>
  );
}
