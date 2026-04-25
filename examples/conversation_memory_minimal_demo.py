"""Minimal runnable demo of cross-session case memory formatting.

Run:
    python examples/conversation_memory_minimal_demo.py
"""

from __future__ import annotations


def build_session_history_document(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message["role"].strip().upper()
        content = message["content"].strip()
        agent_name = message.get("agent_name", "").strip()
        line = f"{role}: {content}"
        if agent_name:
            line = f"{line} (agent={agent_name})"
        lines.append(line)
    return "\n".join(lines)


def build_case_memory_snapshot(
    *,
    session_documents: dict[str, list[str]],
    session_messages: dict[str, list[dict[str, str]]],
) -> dict[str, list[str]]:
    processed_documents: list[str] = []
    for session_id, filenames in session_documents.items():
        processed_documents.extend(filenames)
        processed_documents.append(f"session-{session_id}.txt")
    seeded_messages = [
        build_session_history_document(messages)
        for _session_id, messages in session_messages.items()
    ]
    return {
        "processed_documents": processed_documents,
        "seeded_transcripts": seeded_messages,
    }


if __name__ == "__main__":
    session_messages = {
        "session-1": [
            {"role": "user", "content": "Please review my rental contract.", "agent_name": "User"},
            {
                "role": "assistant",
                "content": "Sure. Upload the document and I will extract key clauses.",
                "agent_name": "LawyerSlovakia",
            },
        ],
        "session-2": [
            {"role": "user", "content": "Here is payment evidence from the second session.", "agent_name": "User"},
            {
                "role": "assistant",
                "content": "I will compare it with the lease obligations.",
                "agent_name": "LawyerSlovakia",
            },
        ],
    }
    session_documents = {
        "session-1": ["lease-session-1.txt"],
        "session-2": ["payment-session-2.txt"],
    }
    snapshot = build_case_memory_snapshot(
        session_documents=session_documents,
        session_messages=session_messages,
    )
    print("Processed documents visible to session 3:")
    for filename in snapshot["processed_documents"]:
        print(f"- {filename}")
    print("\nSeeded transcripts visible to session 3:")
    for transcript in snapshot["seeded_transcripts"]:
        print("---")
        print(transcript)
