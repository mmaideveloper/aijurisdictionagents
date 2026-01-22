from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Source:
    filename: str
    snippet: str


@dataclass
class Message:
    role: str
    agent_name: str
    content: str
    sources: List[Source] = field(default_factory=list)


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: str
    content: str


@dataclass(frozen=True)
class OrchestrationResult:
    final_recommendation: str
    judge_rationale: str
    citations: List[Source]
    messages: List[Message]
