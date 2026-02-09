import { useEffect, useMemo, useState } from "react";
import {
  isAuthProvider,
  setSession,
  type AuthProvider,
  type UserSession
} from "./session";

interface AuthCallbackViewProps {
  onSessionReady: (session: UserSession) => void;
}

interface CallbackParams {
  provider: AuthProvider;
  id: string;
  name: string;
  avatarUrl?: string;
}

function parseCallbackParams(search: string): CallbackParams | null {
  const params = new URLSearchParams(search);
  const provider = params.get("provider");
  const id = params.get("id");
  const name = params.get("name");
  const avatarUrl = params.get("avatarUrl");

  if (!provider || !id || !name || !isAuthProvider(provider)) {
    return null;
  }

  return {
    provider,
    id,
    name,
    avatarUrl: avatarUrl ?? undefined
  };
}

export default function AuthCallbackView({ onSessionReady }: AuthCallbackViewProps) {
  const [error, setError] = useState<string | null>(null);
  const params = useMemo(() => parseCallbackParams(window.location.search), []);

  useEffect(() => {
    if (!params) {
      setError("Invalid auth callback payload. Required: provider, id, and name.");
      return;
    }

    const session: UserSession = {
      id: params.id,
      name: params.name,
      provider: params.provider,
      avatarUrl: params.avatarUrl
    };

    setSession(session);
    onSessionReady(session);
    window.location.replace("/");
  }, [onSessionReady, params]);

  if (error) {
    return (
      <main className="callback callback--error">
        <h1>Authentication failed</h1>
        <p>{error}</p>
        <a className="button primary callback__back" href="/">
          Return to home
        </a>
      </main>
    );
  }

  return (
    <main className="callback">
      <h1>Signing you in</h1>
      <p>Authentication succeeded. Redirecting to the home page.</p>
    </main>
  );
}
