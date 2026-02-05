from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TaskSpec:
    title: str
    body: str


@dataclass(frozen=True)
class IssueRef:
    number: int
    title: str
    url: str
    state: Optional[str] = None


@dataclass(frozen=True)
class ProjectItem:
    issue_number: int
    title: str
    url: str
    status: str
