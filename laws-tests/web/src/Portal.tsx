import React, { useEffect, useState } from "react";

export async function request(
  path: string,
  csrf = "",
  body?: unknown,
  method = "GET",
) {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRF-Token": csrf,
    },
    ...(body === undefined
      ? {}
      : { body: body instanceof FormData ? body : JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Skontrolujte vyplnené údaje.",
    );
  return data;
}
type Access = { test_id: string; status: string };
type Me = {
  csrf: string;
  isAdmin: boolean;
  approved: boolean;
  access: Access[];
};
type Bank = {
  id: string;
  name: string;
  description: string;
  status: string;
  subject: string;
  categories: string[];
  bank_tags: string[];
  exam_categories: string[];
  version: string;
  starts_at: string | null;
  expires_at: string | null;
  rights_confirmed: boolean;
  source_links: string[];
  legal_date: string | null;
  requires_legal_date: boolean;
};
type User = {
  user_id: string;
  email?: string;
  approved: boolean;
  access: Access[];
};
type Q = {
  id?: string;
  category: string;
  number: number;
  title: string;
  body: string;
  answer: string | null;
  subquestions: { id?: string; body: string; answer: string }[];
  tags: string[];
  options: string[];
  related_ids?: string[];
  enabled?: boolean;
  revision?: number;
  source_pages?: number[];
  issues?: string[];
  legal_references?: object[];
};
type Job = {
  id: string;
  test_id: string;
  kind: string;
  status: string;
  cursor: number;
  total: number;
  error_code: string | null;
  result?: any[];
  provider: string;
  model: string;
};
const login = () => {
  location.href =
    "/api/auth/start?return_path=" +
    encodeURIComponent(location.pathname + location.search);
};
const split = (value: string) =>
  value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
function localDateTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
const freshQuestion = (category = ""): Q => ({
  category,
  number: 1,
  title: "",
  body: "",
  answer: "",
  subquestions: [],
  tags: [],
  options: [],
  enabled: false,
  revision: 1,
});
function cleanQuestion(q: Q) {
  return {
    category: q.category,
    number: q.number,
    title: q.title,
    body: q.body,
    answer: q.subquestions.length ? null : q.answer,
    subquestions: q.subquestions,
    tags: q.tags,
    options: q.options || [],
    related_ids: q.related_ids || [],
    enabled: q.enabled ?? false,
    revision: q.revision || 1,
    source_pages: q.source_pages || [],
    legal_references: q.legal_references || [],
  };
}

function QuestionEditor({
  value,
  change,
  candidates = [],
}: {
  value: Q;
  change: (q: Q) => void;
  candidates?: Q[];
}) {
  return (
    <div className="editor-grid">
      <label>
        Kategória
        <input
          value={value.category}
          onChange={(e) => change({ ...value, category: e.target.value })}
        />
      </label>
      <label>
        Číslo otázky
        <input
          type="number"
          min="1"
          value={value.number}
          onChange={(e) => change({ ...value, number: Number(e.target.value) })}
        />
      </label>
      <label>
        Názov
        <input
          value={value.title}
          onChange={(e) => change({ ...value, title: e.target.value })}
        />
      </label>
      <label>
        Otázka
        <textarea
          value={value.body}
          onChange={(e) => change({ ...value, body: e.target.value })}
        />
      </label>
      {!value.subquestions.length && (
        <label>
          Pôvodná odpoveď
          <textarea
            value={value.answer || ""}
            onChange={(e) => change({ ...value, answer: e.target.value })}
          />
        </label>
      )}
      {value.subquestions.map((s, i) => (
        <fieldset key={i}>
          <legend>Podotázka {i + 1}</legend>
          {!value.id && (
            <>
              <button
                onClick={() =>
                  change({
                    ...value,
                    subquestions: value.subquestions.filter((_, j) => j !== i),
                  })
                }
              >
                Odstrániť podotázku
              </button>
              <button
                disabled={i === 0}
                onClick={() => {
                  const next = [...value.subquestions];
                  [next[i - 1], next[i]] = [next[i], next[i - 1]];
                  change({ ...value, subquestions: next });
                }}
              >
                Posunúť podotázku vyššie
              </button>
            </>
          )}
          <label>
            Otázka
            <textarea
              value={s.body}
              onChange={(e) =>
                change({
                  ...value,
                  subquestions: value.subquestions.map((v, j) =>
                    j === i ? { ...v, body: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
          <label>
            Odpoveď
            <textarea
              value={s.answer}
              onChange={(e) =>
                change({
                  ...value,
                  subquestions: value.subquestions.map((v, j) =>
                    j === i ? { ...v, answer: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
        </fieldset>
      ))}
      {!value.id && (
        <button
          onClick={() =>
            change({
              ...value,
              answer: null,
              subquestions: [...value.subquestions, { body: "", answer: "" }],
            })
          }
        >
          Pridať podotázku
        </button>
      )}
      <label>
        Štítky (oddelené čiarkou)
        <input
          defaultValue={value.tags.join(", ")}
          key={value.tags.join(",")}
          onBlur={(e) => change({ ...value, tags: split(e.target.value) })}
        />
      </label>
      {!!value.id && (
        <fieldset>
          <legend>Súvisiace otázky</legend>
          {candidates
            .filter((q) => q.id !== value.id)
            .map((q) => (
              <label key={q.id}>
                <input
                  type="checkbox"
                  checked={(value.related_ids || []).includes(q.id!)}
                  onChange={(e) =>
                    change({
                      ...value,
                      related_ids: e.target.checked
                        ? [...(value.related_ids || []), q.id!]
                        : (value.related_ids || []).filter((id) => id !== q.id),
                    })
                  }
                />
                {q.category}–{q.number} {q.title}
              </label>
            ))}
        </fieldset>
      )}
      <label>
        Možnosti odpovede (jeden riadok = jedna možnosť)
        <textarea
          value={(value.options || []).join("\n")}
          onChange={(e) =>
            change({ ...value, options: e.target.value.split("\n") })
          }
        />
      </label>
      <label>
        <input
          type="checkbox"
          checked={value.enabled ?? false}
          onChange={(e) => change({ ...value, enabled: e.target.checked })}
        />{" "}
        Otázka aktívna
      </label>
      {!!value.source_pages?.length && (
        <p>Zdrojové strany: {value.source_pages.join(", ")}</p>
      )}
      {!!value.issues?.length && (
        <p role="alert">Na kontrolu: {value.issues.join("; ")}</p>
      )}
    </div>
  );
}

function UserApproval({
  user,
  banks,
  save,
}: {
  user: User;
  banks: Bank[];
  save: (approved: boolean, ids: string[]) => void;
}) {
  const [approved, setApproved] = useState(user.approved);
  const [ids, setIds] = useState(
    user.access.filter((a) => a.status === "approved").map((a) => a.test_id),
  );
  return (
    <article className="portal-card">
      <h3>Účet {user.email || user.user_id}</h3>
      <p>
        Žiadosti:{" "}
        {user.access
          .filter((a) => a.status === "pending")
          .map((a) => banks.find((b) => b.id === a.test_id)?.name || a.test_id)
          .join(", ") || "Žiadna čakajúca žiadosť"}
      </p>
      <label>
        <input
          type="checkbox"
          checked={approved}
          onChange={(e) => setApproved(e.target.checked)}
        />{" "}
        Schválený používateľ
      </label>
      {banks.map((b) => (
        <label key={b.id}>
          <input
            type="checkbox"
            checked={ids.includes(b.id)}
            onChange={(e) =>
              setIds(
                e.target.checked
                  ? [...ids, b.id]
                  : ids.filter((id) => id !== b.id),
              )
            }
          />
          {b.name}
        </label>
      ))}
      <button onClick={() => setIds(banks.map((b) => b.id))}>
        Vybrať aktuálne banky
      </button>
      <button className="primary" onClick={() => save(approved, ids)}>
        Uložiť prístupy
      </button>
      <button onClick={() => save(false, [])}>Odobrať všetky prístupy</button>
    </article>
  );
}

function Admin({ me }: { me: Me }) {
  const [tab, setTab] = useState("banks"),
    [banks, setBanks] = useState<Bank[]>([]),
    [users, setUsers] = useState<User[]>([]),
    [jobs, setJobs] = useState<Job[]>([]);
  const [bank, setBank] = useState<Bank | null>(null),
    [questions, setQuestions] = useState<Q[]>([]),
    [question, setQuestion] = useState<Q | null>(null);
  const [job, setJob] = useState<Job | null>(null),
    [sources, setSources] = useState<{ index: number; pages: number }[]>([]),
    [drafts, setDrafts] = useState<Q[]>([]);
  const [files, setFiles] = useState<File[]>([]),
    [authorized, setAuthorized] = useState(false),
    [selected, setSelected] = useState<string[]>([]);
  const [instruction, setInstruction] = useState(""),
    [rubric, setRubric] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const api = (
    path: string,
    body?: unknown,
    method = body === undefined ? "GET" : "POST",
  ) => request(path, me.csrf, body, method);
  async function refresh() {
    const [b, u, j] = await Promise.all([
      api("/admin/banks"),
      api("/admin/users"),
      api("/admin/jobs"),
    ]);
    setBanks(b);
    setUsers(u);
    setJobs(j);
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice("Uložené.");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    const id = setInterval(() => {
      void refresh().catch((e) => setError(e.message));
    }, 5000);
    return () => clearInterval(id);
  }, []);
  async function openBank(b: Bank) {
    setBank(b);
    setQuestions(await api(`/admin/banks/${b.id}/questions`));
    setSelected([]);
    setQuestion(null);
  }
  const newBank = () =>
    setBank({
      id: "",
      name: "",
      description: "",
      subject: "",
      categories: ["general"],
      bank_tags: [],
      exam_categories: [],
      version: "1",
      status: "draft",
      starts_at: null,
      expires_at: null,
      rights_confirmed: false,
      source_links: [],
      legal_date: null,
      requires_legal_date: false,
    });
  async function openJob(j: Job) {
    const detail = await api("/admin/jobs/" + j.id);
    setJob(detail);
    setSources(
      detail.kind === "import"
        ? await api("/admin/jobs/" + j.id + "/sources")
        : [],
    );
    setDrafts(
      detail.kind === "import"
        ? detail.result.map((r: Q) => ({ ...freshQuestion(), ...r }))
        : [],
    );
  }
  return (
    <section className="portal-content">
      <h1>Správa testov</h1>
      <nav className="modebar">
        <button onClick={() => setTab("banks")}>Banky a import</button>
        <button onClick={() => setTab("users")}>
          Žiadosti a schválení používatelia
        </button>
        <button onClick={() => setTab("jobs")}>Importy a AI štítky</button>
      </nav>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <fieldset disabled={busy} className="portal-fieldset">
        {tab === "users" && (
          <>
            <p>
              Schváľte účet a konkrétne banky. Nové banky sa nepridávajú
              automaticky.
            </p>
            {users.length === 0 && <p>Zatiaľ žiadne žiadosti.</p>}
            {users.map((u) => (
              <UserApproval
                key={u.user_id + JSON.stringify(u)}
                user={u}
                banks={banks}
                save={(approved, bank_ids) =>
                  void run(async () => {
                    await api(
                      "/admin/users/" + u.user_id,
                      { approved, bank_ids },
                      "PUT",
                    );
                  })
                }
              />
            ))}
          </>
        )}
        {tab === "banks" && (
          <>
            <button onClick={newBank}>Nová banka</button>
            <div className="catalogue">
              {banks.map((b) => (
                <button key={b.id} onClick={() => void run(() => openBank(b))}>
                  {b.name} · {b.status}
                </button>
              ))}
            </div>
            {bank && (
              <article className="portal-card">
                <h2>{bank.name || "Nová banka"}</h2>
                <div className="editor-grid">
                  <label>
                    Identifikátor
                    <input
                      value={bank.id}
                      disabled={banks.some((b) => b.id === bank.id)}
                      onChange={(e) => setBank({ ...bank, id: e.target.value })}
                    />
                  </label>
                  <label>
                    Názov
                    <input
                      value={bank.name}
                      onChange={(e) =>
                        setBank({ ...bank, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Popis / fakulta / skúška
                    <textarea
                      value={bank.description}
                      onChange={(e) =>
                        setBank({ ...bank, description: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Predmet
                    <input
                      value={bank.subject}
                      onChange={(e) =>
                        setBank({ ...bank, subject: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Edícia
                    <input
                      value={bank.version}
                      onChange={(e) =>
                        setBank({ ...bank, version: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Kategórie
                    <input
                      defaultValue={bank.categories.join(", ")}
                      key={bank.id}
                      onBlur={(e) =>
                        setBank({ ...bank, categories: split(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    Kategórie skúšky
                    <input
                      defaultValue={bank.exam_categories.join(", ")}
                      key={bank.id}
                      onBlur={(e) =>
                        setBank({
                          ...bank,
                          exam_categories: split(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Štítky banky
                    <input
                      defaultValue={(bank.bank_tags || []).join(", ")}
                      key={bank.id}
                      onBlur={(e) =>
                        setBank({ ...bank, bank_tags: split(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    Začiatok
                    <input
                      type="datetime-local"
                      value={localDateTime(bank.starts_at)}
                      onChange={(e) =>
                        setBank({
                          ...bank,
                          starts_at: e.target.value
                            ? new Date(e.target.value).toISOString()
                            : null,
                        })
                      }
                    />
                  </label>
                  <label>
                    Koniec
                    <input
                      type="datetime-local"
                      value={localDateTime(bank.expires_at)}
                      onChange={(e) =>
                        setBank({
                          ...bank,
                          expires_at: e.target.value
                            ? new Date(e.target.value).toISOString()
                            : null,
                        })
                      }
                    />
                  </label>
                  <label>
                    Dátum právneho stavu (právne banky)
                    <input
                      type="date"
                      value={bank.legal_date || ""}
                      onChange={(e) =>
                        setBank({ ...bank, legal_date: e.target.value || null })
                      }
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={bank.requires_legal_date}
                      onChange={(e) =>
                        setBank({
                          ...bank,
                          requires_legal_date: e.target.checked,
                        })
                      }
                    />
                    Právna banka — vyžaduje presný právny dátum
                  </label>
                  <label>
                    Stav
                    <select
                      value={bank.status}
                      onChange={(e) =>
                        setBank({ ...bank, status: e.target.value })
                      }
                    >
                      <option value="draft">Návrh</option>
                      <option value="published">Publikovaná</option>
                      <option value="withdrawn">Vypnutá</option>
                      {!["draft", "published", "withdrawn"].includes(
                        bank.status,
                      ) && <option value={bank.status}>{bank.status}</option>}
                    </select>
                  </label>
                  <label>
                    Zdrojové odkazy (jeden na riadok)
                    <textarea
                      key={bank.id}
                      defaultValue={bank.source_links.join("\n")}
                      onBlur={(e) =>
                        setBank({
                          ...bank,
                          source_links: e.target.value
                            .split("\n")
                            .filter(Boolean),
                        })
                      }
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={bank.rights_confirmed}
                      onChange={(e) =>
                        setBank({ ...bank, rights_confirmed: e.target.checked })
                      }
                    />{" "}
                    Mám overené oprávnenie sprístupniť tento obsah a vykonal som
                    kontrolu.
                  </label>
                </div>
                <button
                  className="primary"
                  onClick={() =>
                    void run(async () => {
                      const keys = [
                        "id",
                        "name",
                        "description",
                        "subject",
                        "categories",
                        "bank_tags",
                        "exam_categories",
                        "version",
                        "status",
                        "starts_at",
                        "expires_at",
                        "rights_confirmed",
                        "source_links",
                        "legal_date",
                        "requires_legal_date",
                      ];
                      await api(
                        "/admin/banks/" + bank.id,
                        Object.fromEntries(
                          keys.map((k) => [k, (bank as any)[k]]),
                        ),
                        "PUT",
                      );
                    })
                  }
                >
                  Uložiť banku
                </button>
                {banks.some((b) => b.id === bank.id) && (
                  <>
                    <h3>Import PDF alebo obrázkov strán</h3>
                    <p>
                      Najviac 500 strán / 100 MB. AI spracuje zdroj; výsledok
                      pred zaradením skontrolujete. Importované otázky zostanú
                      neaktívne. Zdroj aj vybrané otázky sa spracujú pomocou
                      Azure Foundry. Neposielajte osobné údaje.
                    </p>
                    <input
                      aria-label="Zdrojové súbory"
                      type="file"
                      multiple
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(e) =>
                        setFiles(Array.from(e.target.files || []))
                      }
                    />
                    <ol>
                      {files.map((f, i) => (
                        <li key={i}>
                          {f.name}{" "}
                          <button
                            disabled={i === 0}
                            onClick={() => {
                              const next = [...files];
                              [next[i - 1], next[i]] = [next[i], next[i - 1]];
                              setFiles(next);
                            }}
                          >
                            Posunúť vyššie
                          </button>
                        </li>
                      ))}
                    </ol>
                    <label>
                      <input
                        type="checkbox"
                        checked={authorized}
                        onChange={(e) => setAuthorized(e.target.checked)}
                      />{" "}
                      Mám oprávnenie spracovať zdroj pomocou AI.
                    </label>
                    <button
                      disabled={!files.length || !authorized}
                      onClick={() =>
                        void run(async () => {
                          const data = new FormData();
                          files.forEach((f) => data.append("files", f));
                          data.append("authorized", "true");
                          await api(`/admin/banks/${bank.id}/imports`, data);
                          setTab("jobs");
                        })
                      }
                    >
                      Spustiť import
                    </button>
                    <h3>Otázky a odpovede</h3>
                    <button
                      onClick={() =>
                        setQuestion(freshQuestion(bank.categories[0]))
                      }
                    >
                      Nová otázka
                    </button>
                    <button
                      onClick={() => setSelected(questions.map((q) => q.id!))}
                    >
                      Vybrať všetky otázky
                    </button>
                    <button onClick={() => setSelected([])}>
                      Zrušiť výber
                    </button>
                    {[true, false].map((enabled) => (
                      <button
                        key={String(enabled)}
                        disabled={!selected.length}
                        onClick={() =>
                          void run(async () => {
                            await api(
                              `/admin/banks/${bank.id}/question-status`,
                              {
                                enabled,
                                questions: questions
                                  .filter((q) => selected.includes(q.id!))
                                  .map((q) => ({
                                    id: q.id,
                                    revision: q.revision || 1,
                                  })),
                              },
                            );
                            await openBank(bank);
                          })
                        }
                      >
                        {enabled ? "Aktivovať vybrané" : "Vypnúť vybrané"}
                      </button>
                    ))}
                    {questions.map((q) => (
                      <div className="question-row" key={q.id}>
                        <label>
                          <input
                            type="checkbox"
                            checked={selected.includes(q.id!)}
                            onChange={(e) =>
                              setSelected(
                                e.target.checked
                                  ? [...selected, q.id!]
                                  : selected.filter((v) => v !== q.id),
                              )
                            }
                          />
                          {q.category}–{q.number} {q.title} ·{" "}
                          {q.enabled ? "aktívna" : "vypnutá"}
                        </label>
                        <button onClick={() => setQuestion(q)}>Upraviť</button>
                      </div>
                    ))}
                    {question && (
                      <>
                        <QuestionEditor
                          key={question.id || "new"}
                          value={question}
                          change={setQuestion}
                          candidates={questions}
                        />
                        <button
                          className="primary"
                          onClick={() =>
                            void run(async () => {
                              await api(
                                `/admin/banks/${bank.id}/questions${question.id ? "/" + question.id : ""}`,
                                cleanQuestion(question),
                                question.id ? "PUT" : "POST",
                              );
                              await openBank(bank);
                            })
                          }
                        >
                          Uložiť otázku
                        </button>
                      </>
                    )}
                    <h3>AI označovanie vybraných otázok ({selected.length})</h3>
                    <label>
                      Požiadavka
                      <textarea
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder="Rozdeľ podľa ročníkov gymnázia…"
                      />
                    </label>
                    <label>
                      Pravidlá / učebné osnovy
                      <textarea
                        value={rubric}
                        onChange={(e) => setRubric(e.target.value)}
                        placeholder="Uveďte rámec pre každý ročník alebo tému."
                      />
                    </label>
                    <button
                      disabled={
                        !selected.length ||
                        instruction.length < 5 ||
                        rubric.length < 5
                      }
                      onClick={() =>
                        void run(async () => {
                          await api(`/admin/banks/${bank.id}/tagging`, {
                            question_ids: selected,
                            instruction,
                            rubric,
                          });
                          setTab("jobs");
                        })
                      }
                    >
                      Navrhnúť AI štítky
                    </button>
                  </>
                )}
              </article>
            )}
          </>
        )}
        {tab === "jobs" && (
          <>
            <p>
              AI návrhy vyžadujú vašu kontrolu. Chybnú úlohu možno opakovať bez
              straty dokončených strán.
            </p>
            {jobs.map((j) => (
              <article className="portal-card" key={j.id}>
                <h3>
                  {banks.find((b) => b.id === j.test_id)?.name} ·{" "}
                  {j.kind === "import" ? "Import" : "AI štítky"}
                </h3>
                <p>
                  {j.status} · {j.cursor}/{j.total} · {j.provider}/{j.model}
                </p>
                {j.error_code && (
                  <p role="alert">
                    Spracovanie zlyhalo. Skontrolujte dostupnosť modelu alebo
                    súbory a skúste znova.
                  </p>
                )}
                <button onClick={() => void run(() => openJob(j))}>
                  Otvoriť návrh
                </button>
                {["error", "cancelled"].includes(j.status) && (
                  <button
                    onClick={() =>
                      void run(async () => {
                        await api(`/admin/jobs/${j.id}/retry`, {});
                      })
                    }
                  >
                    Opakovať
                  </button>
                )}
                {!["applied", "cancelled"].includes(j.status) && (
                  <button
                    onClick={() =>
                      void run(async () => {
                        await api(`/admin/jobs/${j.id}/cancel`, {});
                      })
                    }
                  >
                    Zrušiť
                  </button>
                )}
                {j.kind === "tagging" && j.status === "applied" && (
                  <button
                    onClick={() =>
                      void run(async () => {
                        await api(`/admin/jobs/${j.id}/undo`, {});
                      })
                    }
                  >
                    Vrátiť túto dávku štítkov
                  </button>
                )}
              </article>
            ))}
            {job && (
              <article className="portal-card">
                <h2>Kontrola návrhu</h2>
                {job.kind === "import" && (
                  <p>Počet navrhnutých otázok: {drafts.length}</p>
                )}
                {sources.map((s) => (
                  <p key={s.index}>
                    <a
                      target="_blank"
                      rel="noreferrer"
                      href={`/api/admin/jobs/${job.id}/sources/${s.index}`}
                    >
                      Zdroj {s.index + 1} ({s.pages} strán)
                    </a>
                  </p>
                ))}
                {job.kind === "import" ? (
                  <>
                    {drafts.map((q, i) => (
                      <details key={i}>
                        <summary>
                          {q.category}–{q.number}: {q.title}{" "}
                          {q.issues?.length ? " · potrebuje opravu" : ""}
                        </summary>
                        <QuestionEditor
                          value={q}
                          change={(value) =>
                            setDrafts((v) =>
                              v.map((r, j) => (j === i ? value : r)),
                            )
                          }
                        />
                        <button
                          onClick={() =>
                            setDrafts((v) => v.filter((_, j) => j !== i))
                          }
                        >
                          Vynechať tento záznam
                        </button>
                      </details>
                    ))}
                    <button
                      disabled={job.status !== "review"}
                      onClick={() =>
                        void run(async () => {
                          await api(
                            `/admin/jobs/${job.id}/review`,
                            { records: drafts.map(cleanQuestion) },
                            "PUT",
                          );
                          await openJob(job);
                        })
                      }
                    >
                      Potvrdiť opravy a uložiť kontrolu
                    </button>
                  </>
                ) : (
                  <ul>
                    {job.result?.map((r, i) => (
                      <li key={i}>
                        <strong>{r.label || r.id}</strong>
                        {r.body && <p>{r.body}</p>}
                        {!!r.subquestions?.length && (
                          <ol>
                            {r.subquestions.map(
                              (body: string, index: number) => (
                                <li key={index}>{body}</li>
                              ),
                            )}
                          </ol>
                        )}
                        {r.tags.join(", ")} — {r.rationale}{" "}
                        {!!r.related_ids?.length && (
                          <span>
                            Súvisiace otázky: {r.related_ids.join(", ")}
                          </span>
                        )}
                        {r.uncertain &&
                          " · neistý návrh, upravte pravidlá alebo označte ručne"}
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  className="primary"
                  disabled={job.status !== "review"}
                  onClick={() =>
                    void run(async () => {
                      await api(`/admin/jobs/${job.id}/apply`, {});
                      await openJob(job);
                    })
                  }
                >
                  Schváliť a zaradiť{" "}
                  {job.kind === "import" ? "neaktívne otázky" : "štítky"}
                </button>
              </article>
            )}
          </>
        )}
      </fieldset>
    </section>
  );
}

function Study({ bank, me, read }: { bank: Bank; me: Me; read: () => void }) {
  const [questions, setQuestions] = useState<Q[]>([]),
    [search, setSearch] = useState(""),
    [tags, setTags] = useState(""),
    [category, setCategory] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [name, setName] = useState(""),
    [editingId, setEditingId] = useState<string | null>(null),
    [sets, setSets] = useState<any[]>([]),
    [error, setError] = useState("");
  const api = (p: string, b?: unknown, m = b === undefined ? "GET" : "POST") =>
    request(p, me.csrf, b, m);
  const refresh = () => api("/study-sets").then(setSets);
  useEffect(() => {
    let current = true;
    void api(
      `/tests/${bank.id}/questions?search=${encodeURIComponent(search)}&tags=${encodeURIComponent(tags)}&category=${encodeURIComponent(category)}`,
    )
      .then((q) => {
        if (current) setQuestions(q);
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [search, tags, category, bank.id]);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, []);
  const run = async (fn: () => Promise<void>) => {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="portal-content">
      <h1>{bank.name}</h1>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button onClick={read}>Otvoriť otázky a precvičovanie</button>
      <h2>Môj študijný výber</h2>
      <div className="editor-grid">
        <label>
          Hľadať
          <input value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <label>
          Kategória
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Všetky</option>
            {bank.categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          Štítky
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="subject:biology, school-year:1, school-year:2"
          />
        </label>
      </div>
      <p>
        V jednej skupine štítkov stačí jedna zhoda; medzi skupinami musia platiť
        všetky podmienky.
      </p>
      <button
        onClick={() =>
          setSelected(
            Array.from(new Set([...selected, ...questions.map((q) => q.id!)])),
          )
        }
      >
        Pridať všetky výsledky
      </button>
      <button
        onClick={() => {
          setSelected([]);
          setEditingId(null);
          setName("");
        }}
      >
        Nový prázdny výber
      </button>
      {questions.map((q) => (
        <label className="question-row" key={q.id}>
          <input
            type="checkbox"
            checked={selected.includes(q.id!)}
            onChange={(e) =>
              setSelected(
                e.target.checked
                  ? [...selected, q.id!]
                  : selected.filter((id) => id !== q.id),
              )
            }
          />
          {q.category}–{q.number} {q.title} <small>{q.tags.join(", ")}</small>
        </label>
      ))}
      <label>
        Názov výberu
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <button
        className="primary"
        disabled={!name.trim() || !selected.length}
        onClick={() =>
          void run(async () => {
            await api(
              editingId ? "/study-sets/" + editingId : "/study-sets",
              {
                test_id: bank.id,
                name,
                question_ids: selected,
              },
              editingId ? "PUT" : "POST",
            );
            await refresh();
          })
        }
      >
        Uložiť výber ({selected.length})
      </button>
      <h2>Uložené výbery</h2>
      {sets
        .filter((s) => s.test_id === bank.id)
        .map((s) => (
          <article className="portal-card" key={s.id}>
            <h3>{s.name}</h3>
            <p>{s.question_ids.length} otázok</p>
            <button
              onClick={() => {
                setSelected(s.question_ids);
                setName(s.name);
                setEditingId(s.id);
              }}
            >
              Načítať výber
            </button>
            <button
              onClick={() => {
                history.replaceState(
                  {},
                  "",
                  `/?test=${encodeURIComponent(bank.id)}&studySet=${s.id}`,
                );
                read();
              }}
            >
              Precvičovať výber
            </button>
            <button
              onClick={() =>
                void run(async () => {
                  await api("/study-sets/" + s.id, undefined, "DELETE");
                  await refresh();
                })
              }
            >
              Odstrániť
            </button>
          </article>
        ))}
    </section>
  );
}

export function Portal({ Reader }: { Reader: React.ComponentType }) {
  const [me, setMe] = useState<Me | null>(null),
    [banks, setBanks] = useState<Bank[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [view, setView] = useState("catalogue"),
    [bank, setBank] = useState<Bank | null>(null);
  async function refresh(resolveLink = false) {
    const [b, m] = await Promise.all([
      request("/tests"),
      request("/me").catch(() => null),
    ]);
    setBanks(b);
    setMe(m);
    setLoading(false);
    if (resolveLink && m) {
      const query = new URLSearchParams(location.search);
      const requested = b.find((v: Bank) => v.id === query.get("test"));
      if (
        requested &&
        (query.has("question") || query.has("studySet")) &&
        (m.isAdmin ||
          (m.approved &&
            m.access.some(
              (a: Access) =>
                a.test_id === requested.id && a.status === "approved",
            )))
      ) {
        setBank(requested);
        setView("reader");
      }
    }
  }
  useEffect(() => {
    void refresh(true).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, []);
  const allowed = (id: string) =>
    !!me &&
    (me.isAdmin ||
      (me.approved &&
        me.access.some((a) => a.test_id === id && a.status === "approved")));
  if (view === "reader")
    return (
      <>
        <div className="portal-return">
          <button
            onClick={() => {
              setView("catalogue");
              void refresh();
            }}
          >
            ← Všetky banky
          </button>
        </div>
        <Reader />
      </>
    );
  return (
    <>
      <header className="topbar">
        <a className="brand" href="/">
          JurisDigta · Testy
        </a>
        <nav>
          <button
            onClick={() => {
              setView("catalogue");
              void refresh();
            }}
          >
            Všetky banky
          </button>
          {me?.isAdmin && (
            <button onClick={() => setView("admin")}>Správa testov</button>
          )}
          {me ? (
            <button
              onClick={async () => {
                await request("/logout", me.csrf, {}, "POST");
                setMe(null);
                setView("catalogue");
              }}
            >
              Odhlásiť sa
            </button>
          ) : (
            <button className="primary" onClick={login}>
              Registrácia / prihlásenie
            </button>
          )}
        </nav>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {view === "admin" && me?.isAdmin ? (
        <Admin me={me} />
      ) : view === "study" && me && bank ? (
        <Study
          bank={bank}
          me={me}
          read={() => {
            if (!location.search.includes("studySet="))
              history.replaceState(
                {},
                "",
                `/?test=${encodeURIComponent(bank.id)}`,
              );
            setView("reader");
          }}
        />
      ) : (
        <main>
          <section className="intro">
            <div>
              <div className="eyebrow">PRÍPRAVA VLASTNÝM TEMPOM</div>
              <h1>
                Vaše vedomosti.
                <br />
                Váš študijný plán.
              </h1>
              <p>
                Vyberte si banku otázok. Po registrácii požiadajte o prístup.
                <br />
                Administrátor schváli konkrétne banky pre váš účet.
              </p>
            </div>
          </section>
          {loading ? (
            <p>Načítavam banky…</p>
          ) : (
            <section className="catalogue">
              {banks.map((b) => (
                <article className="portal-card" key={b.id}>
                  <span className="pill">
                    {b.status === "preview"
                      ? "Neúplná ukážka"
                      : "Študijná banka"}
                  </span>
                  <h2>{b.name}</h2>
                  <p>{b.description}</p>
                  <p>
                    Edícia {b.version}
                    {b.expires_at &&
                      ` · do ${new Date(b.expires_at).toLocaleDateString("sk")}`}
                  </p>
                  {allowed(b.id) ? (
                    <button
                      className="primary"
                      onClick={() => {
                        history.replaceState(
                          {},
                          "",
                          `/?test=${encodeURIComponent(b.id)}`,
                        );
                        setBank(b);
                        setView("study");
                      }}
                    >
                      Otvoriť banku
                    </button>
                  ) : !me ? (
                    <button onClick={login}>
                      Zaregistrovať sa a požiadať o prístup
                    </button>
                  ) : (
                    <>
                      <p>
                        {me.access.find((a) => a.test_id === b.id)?.status ===
                        "pending"
                          ? "Žiadosť čaká na schválenie."
                          : me.access.find((a) => a.test_id === b.id)
                                ?.status === "rejected"
                            ? "Žiadosť nebola schválená."
                            : "Prístup k tejto banke zatiaľ nie je schválený."}
                      </p>
                      <button
                        disabled={me.access.some(
                          (a) => a.test_id === b.id && a.status === "pending",
                        )}
                        onClick={async () => {
                          try {
                            await request(
                              "/access-requests/" + b.id,
                              me.csrf,
                              {},
                              "POST",
                            );
                            await refresh();
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        Požiadať o prístup
                      </button>
                    </>
                  )}
                </article>
              ))}
              {banks.length === 0 && <p>Zatiaľ žiadne publikované banky.</p>}
            </section>
          )}
          <footer>
            Nezávislá študijná príprava · AI návrhy podliehajú ľudskej kontrole.
          </footer>
        </main>
      )}
    </>
  );
}
