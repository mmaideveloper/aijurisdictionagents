import type { UserSession } from "../auth/session";

interface HeaderProps {
  session: UserSession | null;
  onGoogleSignIn: () => void;
  onXSignIn: () => void;
  onLogout: () => void;
  googleEnabled: boolean;
  xEnabled: boolean;
}

export default function Header({
  session,
  onGoogleSignIn,
  onXSignIn,
  onLogout,
  googleEnabled,
  xEnabled
}: HeaderProps) {
  const showProviderHint = !googleEnabled || !xEnabled;

  return (
    <header className="site-header">
      <div className="site-header__brand">
        <span className="site-header__badge">Frontend demo</span>
        <h1>AI Jurisdiction Frontend</h1>
      </div>

      <div className="auth-menu" aria-live="polite">
        {!session ? (
          <>
            <div className="auth-menu__buttons">
              <button
                className="btn btn--primary"
                type="button"
                onClick={onGoogleSignIn}
                disabled={!googleEnabled}
              >
                Continue with Google
              </button>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={onXSignIn}
                disabled={!xEnabled}
              >
                Continue with X
              </button>
            </div>
            {showProviderHint ? (
              <p className="auth-menu__hint">
                Configure <code>VITE_AUTH_GOOGLE_START_URL</code> and{" "}
                <code>VITE_AUTH_X_START_URL</code> to enable sign-in.
              </p>
            ) : null}
          </>
        ) : (
          <div className="auth-menu__session">
            <p>
              Signed in as <strong>{session.name}</strong>
            </p>
            <button className="btn btn--accent" type="button" onClick={onLogout}>
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
