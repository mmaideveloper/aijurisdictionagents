import React, { useEffect, useState } from "react";

export type TextToken = { text: string; href?: string };

export function LegalText({ tokens, text }: { tokens?: TextToken[]; text: string }) {
  return <>{tokens ? tokens.map((token, index) => token.href ?
    <a className="legal-link" key={index} href={token.href} target="_blank" rel="noopener noreferrer"
      title="Otvoriť zákon v novej karte">{token.text}<span className="sr-only"> (nová karta)</span></a>
    : <React.Fragment key={index}>{token.text}</React.Fragment>) : text}</>;
}

type Law = {
  title: string; law_number: number; law_year: number; legal_date: string;
  effective_from: string; effective_to: string | null; source_url: string | null;
  version_token: string; target_found: boolean | null;
  provisions: { anchor: string; heading: string; body_text: string; highlighted: boolean }[];
};

export function LawReader() {
  const [law, setLaw] = useState<Law | null>(null);
  const [error, setError] = useState("");
  const query = new URLSearchParams(location.search);
  const backUrl = query.get("test") ? `/?test=${encodeURIComponent(query.get("test")!)}` : "/";
  const target = query.get("section") ? `§ ${query.get("section")}${query.get("paragraph") ? ` ods. ${query.get("paragraph")}` : ""}${query.get("letter") ? ` písm. ${query.get("letter")})` : ""}` : "";
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api${location.pathname}${location.search}`, { signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Neplatný odkaz na zákon.");
        setLaw(body);
      }).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (law?.target_found) {
      const element = document.querySelector<HTMLElement>(".law-provision.highlighted");
      element?.scrollIntoView({ block: "center" });
      element?.focus({ preventScroll: true });
    }
  }, [law]);
  return <main className="law-reader">
    <header className="law-reader-header"><a href={backUrl}>JurisDigta · Testy</a><span>Verejná knižnica zákonov</span></header>
    {error ? <section className="item" role="alert"><h1>Znenie zákona nie je dostupné</h1><p>{error}</p><a className="legal-link" href={backUrl}>Späť na otázky</a></section>
      : !law ? <p role="status">Načítavam zákon…</p> : <>
        <section className="item">
          <div className="item-label">PREDPIS {law.law_number}/{law.law_year} Z. z.</div>
          <h1>{law.title}</h1>
          <p>Znenie pre test k <strong>{law.legal_date}</strong> · Účinné od {law.effective_from}{law.effective_to ? ` do ${law.effective_to}` : ""}</p>
          {law.source_url && <a className="legal-link" href={law.source_url} target="_blank" rel="noopener noreferrer">Oficiálny zdroj · Slov-Lex ↗</a>}
          {target && <p>Požadované ustanovenie: <strong>{target}</strong></p>}
          {law.target_found === false && <p role="status">Presné ustanovenie sa v tomto znení nepodarilo nájsť. Zobrazujeme dostupný text zákona bez zvýraznenia.</p>}
        </section>
        {law.provisions.map((provision, index) => <article key={index} id={`provision-${index}`}
          className={`item law-provision${provision.highlighted ? " highlighted" : ""}`} tabIndex={-1}>
          {provision.highlighted && <div className="item-label">{target} · VYBRANÉ USTANOVENIE</div>}
          {provision.heading && <h2>{provision.heading}</h2>}
          <p>{provision.body_text}</p>
        </article>)}
      </>}
  </main>;
}
