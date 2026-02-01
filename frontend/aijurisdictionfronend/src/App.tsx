const highlights = [
  {
    title: "Secure Intake",
    body: "Collect user instructions and uploads in a single flow before agents begin."
  },
  {
    title: "Live Orchestration",
    body: "Stream status updates from judge and lawyer agents in real time."
  },
  {
    title: "Traceable Outputs",
    body: "Keep decisions and next steps visible, searchable, and export-ready."
  }
];

const workflow = [
  "Authenticate and start a case session",
  "Upload evidence and set instructions",
  "Watch the agent dialog unfold",
  "Stop or export the final summary"
];

export default function App() {
  return (
    <div className="page">
      <header className="hero">
        <div className="hero__badge">Frontend demo</div>
        <h1>AI Jurisdiction Frontend</h1>
        <p>
          A React + TypeScript starter for the AI Jurisdiction system. Build the
          client workspace, orchestrate live sessions, and keep every decision in view.
        </p>
        <div className="hero__actions">
          <button className="btn btn--primary" type="button">Start session</button>
          <button className="btn btn--ghost" type="button">View agent stream</button>
        </div>
        <div className="hero__panel">
          <div>
            <span className="label">Status</span>
            <p className="value">Awaiting intake</p>
          </div>
          <div>
            <span className="label">Region</span>
            <p className="value">Slovakia (SK)</p>
          </div>
          <div>
            <span className="label">Mode</span>
            <p className="value">Advice</p>
          </div>
        </div>
      </header>

      <section className="grid">
        {highlights.map((item) => (
          <article key={item.title} className="card">
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </article>
        ))}
      </section>

      <section className="callout">
        <div>
          <h2>Workflow snapshot</h2>
          <p>
            This demo layout mirrors the future dashboard: intake on the left,
            streamed dialogue on the right, and actions pinned for clarity.
          </p>
          <ul>
            {workflow.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="callout__panel">
          <span className="label">Next milestone</span>
          <h3>Hook up API events</h3>
          <p>
            Connect to the orchestration endpoints and map the messages to this
            layout in the next iteration.
          </p>
          <button className="btn btn--accent" type="button">Open API docs</button>
        </div>
      </section>
    </div>
  );
}
