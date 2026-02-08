import React from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "../components/LanguageProvider";

const NotFound: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page center">
      <h1>{t("notFoundTitle")}</h1>
      <p>{t("notFoundBody")}</p>
      <Link to="/" className="button ghost">{t("notFoundAction")}</Link>
    </div>
  );
};

export default NotFound;
