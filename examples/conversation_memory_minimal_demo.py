"""Minimal runnable demo of session transcript persistence formatting.

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


if __name__ == "__main__":
    sample_messages = [
        {"role": "user", "content": "Please review my rental contract.", "agent_name": "User"},
        {
            "role": "assistant",
            "content": "Sure. Upload the document and I will extract key clauses.",
            "agent_name": "LawyerSlovakia",
        },
        {"role": "user", "content": "I uploaded it.", "agent_name": "User"},
    ]
    print(build_session_history_document(sample_messages))
