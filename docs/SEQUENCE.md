# Sequence Diagram (High Level)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Orchestrator
    participant Lawyer
    participant Judge
    participant Docs as Document Loader

    User->>Orchestrator: Submit instruction + (optional) documents folder + country (+ language optional)
    Orchestrator->>Docs: Load & rank relevant documents
    Docs-->>Orchestrator: Documents + citations
    Orchestrator->>Lawyer: Provide instruction + documents (optional) + citations
    Lawyer-->>Orchestrator: Advocacy response (uses citations)
    alt Lawyer asks a question
        Orchestrator->>User: Prompt for answer (configurable timeout, default 5 min)
        User-->>Orchestrator: Answer or "no response"
    end
    Orchestrator->>Judge: Provide instruction + discussion history + citations
    Judge-->>Orchestrator: Evaluation, questions, decision
    alt Judge asks a question
        Orchestrator->>User: Prompt for answer (configurable timeout, default 5 min)
        User-->>Orchestrator: Answer or "no response"
    end
    Orchestrator->>User: Prompt for more questions ("finish" to end)
    User-->>Orchestrator: Next question or "finish"
    loop Until time limit or no user response
        Orchestrator->>Lawyer: Continue discussion
        Lawyer-->>Orchestrator: Follow-up response
        Orchestrator->>Judge: Continue discussion
        Judge-->>Orchestrator: Follow-up response
    end
    Orchestrator-->>User: Final recommendation + citations + judge rationale
```
