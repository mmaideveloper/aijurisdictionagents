import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/mockAuth";
import { useLanguage } from "./LanguageProvider";
import { LanguageSwitcher } from "./LanguageSwitcher";

export const Navigation: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { isAuthenticated, user, signOut } = useAuth();
  const [profileOpen, setProfileOpen] = React.useState(false);
  const profileRef = React.useRef<HTMLDivElement | null>(null);
  const profileTriggerRef = React.useRef<HTMLButtonElement | null>(null);
  const profileItemRefs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const closeProfileMenu = React.useCallback(() => {
    setProfileOpen(false);
  }, []);

  const focusMenuItem = React.useCallback((index: number) => {
    const item = profileItemRefs.current[index];
    item?.focus();
  }, []);

  const handleMenuAction = React.useCallback(
    (action: "profile" | "cases" | "logout") => {
      closeProfileMenu();
      if (action === "profile") {
        navigate("/profile");
        return;
      }
      if (action === "cases") {
        navigate("/app/workspace");
        return;
      }
      signOut();
      navigate("/", { replace: true });
    },
    [closeProfileMenu, navigate, signOut]
  );

  const menuOptions = React.useMemo(
    () => [
      { key: "profile" as const, label: t("navMyProfile") },
      { key: "cases" as const, label: t("navMyCases") },
      { key: "logout" as const, label: t("navLogOut") }
    ],
    [t]
  );

  React.useEffect(() => {
    if (!profileOpen) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent | TouchEvent) => {
      if (!profileRef.current) {
        return;
      }
      if (!profileRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeProfileMenu();
        profileTriggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("touchstart", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("touchstart", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [closeProfileMenu, profileOpen]);

  React.useEffect(() => {
    if (!isAuthenticated) {
      closeProfileMenu();
    }
  }, [closeProfileMenu, isAuthenticated]);

  React.useEffect(() => {
    if (profileOpen) {
      focusMenuItem(0);
    }
  }, [focusMenuItem, profileOpen]);

  const handleMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!profileOpen) {
      return;
    }
    const activeIndex = profileItemRefs.current.findIndex(
      (item) => item === document.activeElement
    );
    const lastIndex = menuOptions.length - 1;

    if (event.key === "Escape") {
      event.preventDefault();
      closeProfileMenu();
      profileTriggerRef.current?.focus();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      const nextIndex = activeIndex < 0 || activeIndex >= lastIndex ? 0 : activeIndex + 1;
      focusMenuItem(nextIndex);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      const nextIndex = activeIndex <= 0 ? lastIndex : activeIndex - 1;
      focusMenuItem(nextIndex);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      focusMenuItem(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      focusMenuItem(lastIndex);
      return;
    }

    if (event.key === "Tab") {
      closeProfileMenu();
    }
  };

  const profileName = user?.name ?? "User";
  const profileEmail = user?.email ?? "";
  const profileInitial = profileName.slice(0, 1).toUpperCase();

  return (
    <header className="site-header">
      <nav className="nav">
        {!isAuthenticated ? (
          <Link className="brand nav-brand" to="/">
            <div className="brand-mark" aria-hidden="true">
              AJ
            </div>
            <div className="brand-copy">
              <strong>{t("appName")}</strong>
              <span>{t("tagline")}</span>
            </div>
          </Link>
        ) : null}
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
                ref={profileTriggerRef}
                aria-label={t("navProfile")}
                aria-haspopup="menu"
                aria-expanded={profileOpen}
                aria-controls="profile-menu"
                onClick={() => setProfileOpen((prev) => !prev)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown" && !profileOpen) {
                    event.preventDefault();
                    setProfileOpen(true);
                  }
                }}
              >
                <span className="profile-initials" aria-hidden="true">
                  {profileInitial}
                </span>
              </button>
              {profileOpen ? (
                <div
                  id="profile-menu"
                  className="profile-panel"
                  role="menu"
                  aria-label={t("navProfileMenu")}
                  onKeyDown={handleMenuKeyDown}
                >
                  <div className="profile-name">{profileName}</div>
                  <div className="profile-email">{profileEmail}</div>
                  <div className="profile-divider" aria-hidden="true" />
                  <div className="profile-actions">
                    {menuOptions.map((option, index) => (
                      <button
                        key={option.key}
                        type="button"
                        role="menuitem"
                        ref={(element) => {
                          profileItemRefs.current[index] = element;
                        }}
                        className="profile-menu-item"
                        onClick={() => handleMenuAction(option.key)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </nav>
    </header>
  );
};
