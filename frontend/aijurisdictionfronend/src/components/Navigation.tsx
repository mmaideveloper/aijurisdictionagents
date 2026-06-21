import React from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "./LanguageProvider";
import { LanguageSwitcher } from "./LanguageSwitcher";

type NavigationProps = {
  isSidebarCollapsed?: boolean;
};

export const Navigation: React.FC<NavigationProps> = ({ isSidebarCollapsed = false }) => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { t } = useLanguage();
  const { isAuthenticated, user, signOut } = useAuth();

  const handleMenuAction = React.useCallback(
    (action: "profile" | "cases" | "logout") => {
      if (action === "profile") {
        navigate("/profile");
        return;
      }
      if (action === "cases") {
        navigate("/");
        return;
      }
      signOut();
      navigate("/auth", { replace: true });
    },
    [navigate, signOut]
  );

  const menuOptions = React.useMemo(
    () => [
      { key: "profile" as const, label: t("navMyProfile") },
      { key: "cases" as const, label: t("navMyCases") },
      { key: "logout" as const, label: t("navLogOut") }
    ],
    [t]
  );

  const profileName = user?.name ?? t("commonUser");
  const profileEmail = user?.email ?? "";
  const profileInitial = profileName.slice(0, 1).toUpperCase();
  const showBrand = !isAuthenticated || pathname !== "/" || isSidebarCollapsed;

  return (
    <header className="site-header">
      <nav className="nav">
        {showBrand ? (
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
          {!isAuthenticated ? <NavLink to="/auth">{t("navAuth")}</NavLink> : null}
          <NavLink to="/">{t("navHome")}</NavLink>
          <NavLink to="/pricing">{t("navPricing")}</NavLink>
        </div>
        <div className="nav-actions">
          <LanguageSwitcher />
          {isAuthenticated ? (
            <div className="profile-menu profile-menu--inline">
              <div className="profile-trigger profile-trigger--static" aria-label={t("navProfile")}>
                <span className="profile-initials" aria-hidden="true">
                  {profileInitial}
                </span>
              </div>
              <div className="profile-inline-copy">
                <span className="profile-name">{profileName}</span>
                <span className="profile-email">{profileEmail}</span>
              </div>
              <div className="profile-actions profile-actions--inline" aria-label={t("navProfileMenu")}>
                {menuOptions.map((option) => (
                  <button
                    key={option.key}
                    type="button"
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
      </nav>
    </header>
  );
};
