import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Course = {
  id: string;
  name: string;
  version: string;
  legal_date: string | null;
  status: string;
  expired: boolean;
  categories: string[];
  category_labels: Record<string, string>;
  legal_summary: string;
  case_type: string;
};
type Item = { id: string; body: string; answer: string; sequence?: number };
type Question = Item & {
  test_id: string;
  category: string;
  number: number;
  title: string;
  structure: string;
  subquestions: Item[];
  provenance: string[];
};
type Result = {
  id: string;
  question_id: string;
  subquestion_id: string | null;
  user_answer: string;
  score: number | null;
  passed: boolean | null;
  status: string;
  model: string;
  provider: string;
  created_at: string;
  content_snapshot: { answer: string; body: string };
  result: {
    matchedPoints: string[];
    missingPoints: string[];
    incorrectClaims: string[];
    feedback: string;
  } | null;
};
type Session = { id: string; question_ids: string[]; mode: string };
type Progress = {
  test_id: string;
  category: string;
  total: number;
  answered: number;
  passed: number;
  mastered: number;
};

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Požiadavku sa nepodarilo spracovať.",
    );
  return data;
}

function App() {
  const [progress, setProgress] = useState<Progress[]>([]);
  const [courses, setCourses] = useState<Course[]>([]),
    [course, setCourse] = useState<Course | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]),
    [question, setQuestion] = useState<Question | null>(null);
  const [category, setCategory] = useState("all"),
    [search, setSearch] = useState(""),
    [me, setMe] = useState<{ csrf: string } | null>(null);
  const [session, setSession] = useState<Session | null>(null),
    [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, Result>>({}),
    [expanded, setExpanded] = useState<string[]>([]);
  const [history, setHistory] = useState<Result[] | null>(null),
    [busy, setBusy] = useState<string | null>(null),
    [error, setError] = useState("");
  const [aggregate, setAggregate] = useState<{
    complete: boolean;
    score?: number;
    passed?: boolean;
  } | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [requestIds, setRequestIds] = useState<Record<string, string>>({});
  const labels = course?.category_labels ?? {};
  useEffect(() => {
    if (history)
      api("/progress")
        .then(setProgress)
        .catch((e) => setError(e.message));
  }, [history]);
  useEffect(() => {
    api("/tests")
      .then((rows: Course[]) => {
        setCourses(rows);
        const type = new URLSearchParams(location.search).get("caseType");
        setCourse(rows.find((c) => c.case_type === type) ?? rows[0] ?? null);
      })
      .catch((e) => setError(e.message));
    api("/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);
  useEffect(() => {
    if (course)
      api(`/tests/${course.id}/questions`)
        .then((rows: Question[]) => {
          setQuestions(rows);
          const requested = new URLSearchParams(location.search).get(
            "question",
          );
          const first = rows.find((q) => q.id === requested) ?? rows[0];
          if (first) void openQuestion(first.id, false);
        })
        .catch((e) => setError(e.message));
  }, [course?.id]);
  async function openQuestion(id: string, push = true) {
    setError("");
    setHistory(null);
    try {
      const row = await api("/questions/" + id);
      setQuestion(row);
      setExpanded([]);
      if (push)
        window.history.pushState({}, "", `?question=${encodeURIComponent(id)}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    const listener = () => {
      const id = new URLSearchParams(location.search).get("question");
      if (id) void openQuestion(id, false);
    };
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, []);
  const login = () => {
    window.location.href =
      "/api/auth/start?return_path=" +
      encodeURIComponent(location.pathname + location.search);
  };
  async function mutate(path: string, body: unknown, method = "POST") {
    return api(path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": me?.csrf ?? "",
      },
      ...(body === null ? {} : { body: JSON.stringify(body) }),
    });
  }
  async function start(mode: string, manual = true) {
    if (!me) {
      login();
      return;
    }
    setBusy("start");
    setError("");
    try {
      const s = await mutate("/sessions", {
        test_id: course?.id,
        mode,
        question_id: manual ? question?.id : null,
      });
      setSession(s);
      setAnswers({});
      setResults({});
      setRequestIds({});
      setExpanded([]);
      setAggregate(null);
      await openQuestion(s.question_ids[0]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function submit(item: Item) {
    if (!question || !session) return;
    setBusy(item.id);
    setError("");
    setAggregate(null);
    const requestId = requestIds[item.id] ?? crypto.randomUUID();
    setRequestIds((v) => ({ ...v, [item.id]: requestId }));
    try {
      const result = await mutate("/attempts", {
        session_id: session.id,
        question_id: question.id,
        subquestion_id: question.structure === "grouped" ? item.id : null,
        answer: answers[item.id],
        request_id: requestId,
      });
      if (result.status === "completed") {
        const nextAggregate = await api(`/sessions/${session.id}/result`);
        setResults((v) => ({ ...v, [item.id]: result }));
        setExpanded((v) => [...v, item.id]);
        setAggregate(nextAggregate);
      } else {
        setResults((v) => ({ ...v, [item.id]: result }));
        setError("Vyhodnotenie ešte nie je dokončené. Skontrolujte históriu.");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  const items = question
    ? question.structure === "grouped"
      ? question.subquestions
      : [question]
    : [];
  const filtered = questions.filter(
    (q) =>
      (category === "all" || q.category === category) &&
      `${q.category}-${q.number} ${q.title} ${q.body}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const practice =
    !!session && !!question && session.question_ids.includes(question.id);
  function ResultView({ result }: { result: Result }) {
    return (
      <section
        className={`result ${result.passed ? "pass" : "fail"}`}
        aria-label="Výsledok vyhodnotenia"
      >
        <div className="result-top">
          <strong>
            {result.status === "completed"
              ? result.passed
                ? "✓ Úspešná odpoveď"
                : "↗ Skúste doplniť odpoveď"
              : "Vyhodnotenie nie je dokončené"}
          </strong>
          {result.score !== null && (
            <b>
              {result.score} % · {result.passed ? "Splnené" : "Nesplnené"}
            </b>
          )}
        </div>
        {result.result && (
          <>
            <p>{result.result.feedback}</p>
            <h4>Čo vo vašej odpovedi chýba</h4>
            {result.result.missingPoints.length ? (
              <ul>
                {result.result.missingPoints.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            ) : (
              <p>Žiadne chýbajúce body.</p>
            )}
            {result.result.incorrectClaims.length > 0 && (
              <>
                <h4>Čo treba opraviť</h4>
                <ul>
                  {result.result.incorrectClaims.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </>
            )}
            <details>
              <summary>Správne uvedené body</summary>
              <ul>
                {result.result.matchedPoints.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </details>
          </>
        )}
        <small>
          AI spätná väzba · {result.provider} / {result.model} · nejde o úradnú
          skúšku
        </small>
      </section>
    );
  }
  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="JurisDigta testy">
          <span className="brandmark">J</span>
          <span>
            JurisDigta<small>SKÚŠKY A VEDOMOSTI</small>
          </span>
        </a>
        <nav>
          <a href="https://jurisdigta.eu">
            O JurisDigta <span aria-hidden>↗</span>
          </a>
          {me ? (
            <>
              <button
                onClick={async () => {
                  try {
                    setHistory(await api("/history"));
                    setSession(null);
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Moje výsledky
              </button>
              <button
                onClick={async () => {
                  await mutate("/logout", null);
                  setMe(null);
                  setSession(null);
                  setHistory(null);
                  setResults({});
                }}
              >
                Odhlásiť sa
              </button>
            </>
          ) : (
            <button className="primary" onClick={login}>
              Prihlásiť sa <span aria-hidden>↗</span>
            </button>
          )}
        </nav>
      </header>
      <main>
        <section className="intro">
          <div>
            <div className="eyebrow">VEDOMOSTI, KTORÉ VÁM DODAJÚ ISTOTU</div>
            <h1>Pripravte sa. S porozumením.</h1>
            <p>
              Otázky a pôvodné odpovede na jednom mieste.
              <br />
              Čítajte voľne, precvičujte si vedomosti po prihlásení.
            </p>
          </div>
          <div className="intro-note">
            <span>01</span>
            <p>
              Vaša príprava.
              <br />
              <strong>Vlastným tempom.</strong>
            </p>
          </div>
        </section>
        <section className="course-bar">
          <div>
            <div className="eyebrow">PRÍPRAVA NA CERTIFIKÁCIU</div>
            {courses.length > 1 ? (
              <select
                aria-label="Vyberte test"
                value={course?.id}
                onChange={(e) => {
                  setSession(null);
                  setCourse(
                    courses.find((c) => c.id === e.target.value) ?? null,
                  );
                }}
              >
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            ) : (
              <h2>{course?.name ?? "Načítavam testy…"}</h2>
            )}
            <p>{course?.legal_summary}</p>
          </div>
          <span className="pill">
            {course?.expired
              ? "Platnosť skončila"
              : course?.status === "development"
                ? "Vývojová ukážka · čaká na kontrolu"
                : "Overený obsah"}
            {course?.legal_date && ` · ${course.legal_date}`}
          </span>
        </section>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!course && !error && <p>Načítavam…</p>}
        {courses.length === 0 && (
          <p>Žiadny zverejnený test zatiaľ nie je dostupný.</p>
        )}
        {history ? (
          <section className="reading history">
            <div className="section-head">
              <h2>Moje výsledky</h2>
              <button onClick={() => setHistory(null)}>Späť k otázkam</button>
            </div>
            <p>
              Vaše odpovede a výsledky uchovávame 12 mesiacov. Históriu môžete
              odstrániť aj skôr.
            </p>
            <h3>Pokrok podľa kategórií</h3>
            <p>
              Počíta sa posledná dokončená odpoveď na každú otázku alebo
              podotázku.
            </p>
            <div className="progress-grid">
              {progress
                .filter((p) => p.test_id === course?.id)
                .map((p) => (
                  <div key={p.category}>
                    <strong>
                      {labels[p.category] ?? p.category} · {p.category}
                    </strong>
                    <p>
                      {p.answered} / {p.total} zodpovedaných · {p.passed}{" "}
                      úspešných · {p.mastered} zvládnutých na 95 %
                    </p>
                    <progress
                      max={p.total}
                      value={p.passed}
                      aria-label={`Kategória ${p.category}`}
                    />
                  </div>
                ))}
            </div>
            <div className="actions">
              <button
                onClick={async () => {
                  const data = await api("/export");
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(data, null, 2)], {
                      type: "application/json",
                    }),
                  );
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "moje-vysledky.json";
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Exportovať výsledky
              </button>
              <button
                onClick={async () => {
                  if (confirm("Odstrániť všetky vaše odpovede a výsledky?")) {
                    await mutate("/history", null, "DELETE");
                    setHistory([]);
                    setResults({});
                  }
                }}
              >
                Odstrániť históriu
              </button>
            </div>
            {history.length === 0 ? (
              <p>Zatiaľ nemáte uložené výsledky.</p>
            ) : (
              <>
                <div className="progress">
                  {history.filter((r) => r.passed).length} úspešných odpovedí z{" "}
                  {history.length} pokusov
                </div>
                {history.map((r) => (
                  <article key={r.id}>
                    <h3>{r.question_id}</h3>
                    <p>{r.content_snapshot.body}</p>
                    <p>
                      <strong>Vaša odpoveď:</strong> {r.user_answer}
                    </p>
                    <ResultView result={r} />
                    <details>
                      <summary>Pôvodná odpoveď použitá pri hodnotení</summary>
                      <p style={{ whiteSpace: "pre-wrap" }}>
                        {r.content_snapshot.answer}
                      </p>
                    </details>
                  </article>
                ))}
              </>
            )}
          </section>
        ) : (
          <div className="workspace">
            <aside className={navOpen ? "nav-open" : "nav-closed"}>
              <button
                className="mobile-toggle"
                aria-expanded={navOpen}
                onClick={() => setNavOpen(!navOpen)}
              >
                Vybrať otázku · {question?.category}–{question?.number}{" "}
                {navOpen ? "−" : "+"}
              </button>
              <div className="section-head">
                <h3>Otázky</h3>
                <span>{questions.length}</span>
              </div>
              <label className="search-label">
                Hľadať v otázkach
                <input
                  placeholder="Číslo alebo téma otázky"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <div className="categories">
                <button
                  className={category === "all" ? "selected" : ""}
                  onClick={() => setCategory("all")}
                >
                  Všetky
                </button>
                {(course?.categories ?? []).map((c) => (
                  <button
                    key={c}
                    className={category === c ? "selected" : ""}
                    onClick={() => setCategory(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
              <div className="question-list">
                {filtered.map((q) => (
                  <button
                    key={q.id}
                    className={q.id === question?.id ? "selected" : ""}
                    onClick={() => {
                      setSession(null);
                      setNavOpen(false);
                      void openQuestion(q.id);
                    }}
                  >
                    <span className="question-number">
                      {q.category}–{q.number}
                    </span>
                    <span>
                      {q.title}
                      <small>{labels[q.category] ?? q.category}</small>
                    </span>
                    <span aria-hidden>›</span>
                  </button>
                ))}
                {filtered.length === 0 && (
                  <p>Žiadna otázka nezodpovedá hľadaniu.</p>
                )}
              </div>
              <div className="aside-note">
                <strong>Čítanie je otvorené všetkým.</strong>
                <p>
                  Na precvičovanie a uloženie výsledkov použite svoj účet
                  JurisDigta.
                </p>
              </div>
            </aside>
            <section className="reading">
              {question && (
                <>
                  <div className="breadcrumb">
                    {labels[question.category] ?? question.category}{" "}
                    <span>/</span> Otázka {question.category}–{question.number}
                  </div>
                  <div className="question-heading">
                    <span className="large-number">
                      {question.category}
                      <small>{question.number}</small>
                    </span>
                    <div>
                      <div className="eyebrow">
                        {practice
                          ? session?.mode === "exam"
                            ? "CVIČNÁ SKÚŠKA"
                            : "PRECVIČOVANIE"
                          : "VEREJNÉ ČÍTANIE"}
                      </div>
                      <h2>{question.title}</h2>
                      <p>
                        {items.length}{" "}
                        {items.length === 1
                          ? "otázka s odpoveďou"
                          : "podotázky s odpoveďami"}
                      </p>
                    </div>
                  </div>
                  {!practice && (
                    <div className="modebar">
                      <button
                        className="primary"
                        disabled={!!course?.expired || !!busy}
                        onClick={() => start("learning")}
                      >
                        {me
                          ? "Precvičiť túto otázku"
                          : "Prihlásiť sa a precvičovať"}{" "}
                        <span aria-hidden>→</span>
                      </button>
                      <button
                        disabled={!!course?.expired || !!busy}
                        onClick={() => start("exam", false)}
                      >
                        Cvičná skúška
                      </button>
                      {me && (
                        <button
                          disabled={!!course?.expired || !!busy}
                          onClick={() => start("learning", false)}
                        >
                          Odporučená otázka
                        </button>
                      )}
                    </div>
                  )}
                  {practice && (
                    <div className="notice">
                      Najprv odpovedzte vlastnými slovami. AI porovná odpoveď s
                      predlohou a ukáže, čo vám chýba. Odpoveď a výsledok sa
                      uložia na 12 mesiacov. Neuvádzajte osobné údaje.
                    </div>
                  )}
                  {items.length > 1 && !practice && (
                    <div className="jump">
                      <span>Podotázky</span>
                      {items.map((i, n) => (
                        <a key={i.id} href={"#item-" + i.id}>
                          {n + 1}
                        </a>
                      ))}
                      <button
                        onClick={() =>
                          setExpanded(
                            expanded.length === items.length
                              ? []
                              : items.map((i) => i.id),
                          )
                        }
                      >
                        {expanded.length === items.length
                          ? "Zbaliť všetky odpovede"
                          : "Rozbaliť všetky odpovede"}
                      </button>
                    </div>
                  )}
                  {items.map((item, n) => (
                    <article
                      className="item"
                      id={"item-" + item.id}
                      key={item.id}
                    >
                      <div className="item-label">
                        {question.structure === "grouped"
                          ? `PODOTÁZKA ${n + 1} Z ${items.length}`
                          : "OTÁZKA"}
                      </div>
                      <h3>{item.body}</h3>
                      {practice && (
                        <>
                          <label className="answer-label">
                            Vaša odpoveď
                            <textarea
                              placeholder="Napíšte odpoveď vlastnými slovami…"
                              value={answers[item.id] ?? ""}
                              onChange={(e) => {
                                setAnswers((v) => ({
                                  ...v,
                                  [item.id]: e.target.value,
                                }));
                                setRequestIds((v) => {
                                  const next = { ...v };
                                  delete next[item.id];
                                  return next;
                                });
                              }}
                              disabled={!!busy || !!results[item.id]}
                            />
                          </label>
                          {!results[item.id] && (
                            <button
                              className="primary"
                              disabled={
                                !!busy ||
                                !answers[item.id]?.trim() ||
                                !!course?.expired
                              }
                              onClick={() => submit(item)}
                            >
                              {busy === item.id
                                ? "AI porovnáva odpoveď…"
                                : "Vyhodnotiť odpoveď"}
                            </button>
                          )}
                          {results[item.id] && (
                            <>
                              <ResultView result={results[item.id]} />
                              <button
                                onClick={() => {
                                  setAggregate(null);
                                  setResults((v) => {
                                    const next = { ...v };
                                    delete next[item.id];
                                    return next;
                                  });
                                  setAnswers((v) => ({ ...v, [item.id]: "" }));
                                  setExpanded((v) =>
                                    v.filter((id) => id !== item.id),
                                  );
                                  setRequestIds((v) => {
                                    const next = { ...v };
                                    delete next[item.id];
                                    return next;
                                  });
                                }}
                              >
                                Skúsiť novú odpoveď
                              </button>
                            </>
                          )}
                        </>
                      )}
                      {(!practice || results[item.id]) && (
                        <div className="reference">
                          <button
                            aria-expanded={expanded.includes(item.id)}
                            onClick={() =>
                              setExpanded((v) =>
                                v.includes(item.id)
                                  ? v.filter((id) => id !== item.id)
                                  : [...v, item.id],
                              )
                            }
                          >
                            <span>
                              {expanded.includes(item.id) ? "−" : "+"}
                            </span>{" "}
                            Pôvodná odpoveď
                          </button>
                          {expanded.includes(item.id) && (
                            <div className="answer-text">
                              {item.answer.split("\n").map((p, i) => (
                                <p key={i}>{p}</p>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </article>
                  ))}
                  {aggregate?.complete && (
                    <div
                      className={`result ${aggregate.passed ? "pass" : "fail"}`}
                    >
                      <strong>
                        Celkový výsledok: {aggregate.score} % ·{" "}
                        {aggregate.passed ? "Splnené" : "Nesplnené"}
                      </strong>
                    </div>
                  )}
                  <div className="bottom-nav">
                    {(practice
                      ? session?.question_ids
                      : questions.map((q) => q.id)
                    )?.map((id, i, ids) =>
                      id === question.id ? (
                        <React.Fragment key={id}>
                          <button
                            disabled={i === 0}
                            onClick={() => openQuestion(ids[i - 1])}
                          >
                            ← Predchádzajúca
                          </button>
                          <span>
                            {i + 1} / {ids.length}
                          </span>
                          <button
                            disabled={i === ids.length - 1}
                            onClick={() => openQuestion(ids[i + 1])}
                          >
                            Nasledujúca →
                          </button>
                        </React.Fragment>
                      ) : null,
                    )}
                  </div>
                  {course?.status !== "development" && (
                    <p className="source-note">
                      Nezávislá príprava na skúšku. Nejde o vydanie osvedčenia ani úradné hodnotenie.
                    </p>
                  )}
                </>
              )}
            </section>
          </div>
        )}
        <footer>
          <strong>JurisDigta</strong>
          <span>Porozumieť. Precvičiť. Napredovať.</span>
          <span>Nezávislá príprava · AI spätná väzba</span>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
