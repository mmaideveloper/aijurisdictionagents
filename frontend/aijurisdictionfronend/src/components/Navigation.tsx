import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/mockAuth";
import { useLanguage } from "./LanguageProvider";
import { LanguageSwitcher } from "./LanguageSwitcher";

export const Navigation: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user } = useAuth();
  const [profileOpen, setProfileOpen] = React.useState(false);
  const profileRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!profileOpen) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent) => {
      if (!profileRef.current) {
        return;
      }
      if (!profileRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [profileOpen]);

  React.useEffect(() => {
    if (!isAuthenticated) {
      setProfileOpen(false);
    }
  }, [isAuthenticated]);

  const profileName = user?.name ?? "User";
  const profileEmail = user?.email ?? "";
  const profileInitial = profileName.slice(0, 1).toUpperCase();

  return (
    <header className="site-header">
      <nav className="nav">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            AJ
          </div>
          <div>
            <strong>{t("appName")}</strong>
            <span>{t("tagline")}</span>
          </div>
        </div>
        <div className="nav-links">
          <NavLink to="/">{t("navHome")}</NavLink>
          <NavLink to="/pricing">{t("navPricing")}</NavLink>
          {!isAuthenticated ? (
            <NavLink to="/auth">{t("navAuth")}</NavLink>
          ) : null}
          <NavLink to="/app">{t("navApp")}</NavLink>
        </div>
        <div className="nav-actions">
          <LanguageSwitcher />
          {isAuthenticated ? (
            <div className="profile-menu" ref={profileRef}>
              <button
                className="profile-trigger"
                type="button"
                aria-label={t("navProfile")}
                aria-haspopup="menu"
                aria-expanded={profileOpen}
                onClick={() => setProfileOpen((prev) => !prev)}
              >
                <span className="profile-initials" aria-hidden="true">
                  {profileInitial}
                </span>
              </button>
              {profileOpen ? (
                <div className="profile-panel" role="menu">
                  <div className="profile-name">{profileName}</div>
                  <div className="profile-email">{profileEmail}</div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </nav>
    </header>
  );
};
