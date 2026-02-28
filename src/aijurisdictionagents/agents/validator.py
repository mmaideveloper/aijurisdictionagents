from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..llm import LLMClient


@dataclass(frozen=True)
class EvaluationCriterion:
    """Single scoring axis used for final weighted accuracy."""

    name: str
    description: str
    weight: float


@dataclass(frozen=True)
class ValidatorInputs:
    """Expected legal anchors and context used during evaluation."""

    country: str
    question: str
    expected_points: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class CriterionScore:
    name: str
    score: float
    rationale: str


@dataclass(frozen=True)
class ValidationReport:
    weighted_accuracy: float
    scores: Sequence[CriterionScore]
    summary: str
    contract_similarity: float
    human_likeness: float


DEFAULT_CRITERIA: tuple[EvaluationCriterion, ...] = (
    EvaluationCriterion(
        name="legal_accuracy",
        description="Whether the final answer aligns with expected legal anchors.",
        weight=0.30,
    ),
    EvaluationCriterion(
        name="coverage",
        description="Whether the conversation addresses all key expected points.",
        weight=0.20,
    ),
    EvaluationCriterion(
        name="clarity",
        description="Whether the final answer is concise and understandable.",
        weight=0.10,
    ),
    EvaluationCriterion(
        name="risk_awareness",
        description="Whether caveats/next steps are communicated.",
        weight=0.10,
    ),
    EvaluationCriterion(
        name="human_likeness",
        description="Whether the exchange resembles a human lawyer-client intake conversation.",
        weight=0.15,
    ),
    EvaluationCriterion(
        name="contract_alignment",
        description="Whether the final contract follows public Slovak rental contract patterns.",
        weight=0.15,
    ),
)


class AIAgentsValidator:
    """Evaluates an agent conversation artifact and returns a weighted accuracy score."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        criteria: Sequence[EvaluationCriterion] = DEFAULT_CRITERIA,
    ) -> None:
        if not criteria:
            raise ValueError("criteria must not be empty")
        total_weight = sum(c.weight for c in criteria)
        if total_weight <= 0:
            raise ValueError("criteria weights must be positive")
        self.llm = llm
        self.criteria = tuple(criteria)

    def evaluate_from_file(
        self,
        communication_path: str | Path,
        inputs: ValidatorInputs,
        final_result: str,
        final_contract: str | None = None,
        reference_contracts: Sequence[str] = (),
    ) -> ValidationReport:
        payload = json.loads(Path(communication_path).read_text(encoding="utf-8"))
        return self.evaluate(
            payload,
            inputs,
            final_result,
            final_contract=final_contract,
            reference_contracts=reference_contracts,
        )

    def evaluate(
        self,
        communication_payload: dict[str, Any],
        inputs: ValidatorInputs,
        final_result: str,
        final_contract: str | None = None,
        reference_contracts: Sequence[str] = (),
    ) -> ValidationReport:
        transcript = _extract_transcript(communication_payload)
        heuristic_scores = self._heuristic_scores(transcript, inputs, final_result)
        contract_similarity = _contract_similarity(final_contract or final_result, reference_contracts)
        human_likeness = _human_likeness(transcript)

        heuristic_scores.extend(
            [
                CriterionScore(
                    name="human_likeness",
                    score=human_likeness,
                    rationale="Measures whether the conversation mirrors realistic lawyer-client intake behavior.",
                ),
                CriterionScore(
                    name="contract_alignment",
                    score=contract_similarity,
                    rationale="Measures overlap between generated contract and reference Slovak rental templates.",
                ),
            ]
        )

        if self.llm is None:
            scores = heuristic_scores
            summary = _build_summary(scores)
        else:
            llm_scores, summary = self._llm_scores(heuristic_scores, transcript, inputs, final_result)
            scores = llm_scores or heuristic_scores

        weighted_accuracy = _weighted_accuracy(scores, self.criteria)
        return ValidationReport(
            weighted_accuracy=weighted_accuracy,
            scores=scores,
            summary=summary,
            contract_similarity=contract_similarity,
            human_likeness=human_likeness,
        )

    def _heuristic_scores(
        self,
        transcript: str,
        inputs: ValidatorInputs,
        final_result: str,
    ) -> list[CriterionScore]:
        expected_tokens = _tokens(" ".join(inputs.expected_points))
        final_tokens = _tokens(final_result)
        transcript_tokens = _tokens(transcript)

        legal_overlap = _safe_ratio(len(expected_tokens & final_tokens), max(1, len(expected_tokens)))
        coverage_overlap = _safe_ratio(len(expected_tokens & transcript_tokens), max(1, len(expected_tokens)))

        sentence_count = max(1, len([s for s in re.split(r"[.!?]+", final_result) if s.strip()]))
        has_structured_clauses = bool(re.search(r"\b\d+\)", final_result))
        if has_structured_clauses:
            clarity = 0.9
        else:
            clarity = min(1.0, 1 / sentence_count + 0.4)

        risk_markers = {
            "risk", "uncertain", "depends", "recommend", "consult", "limitation", "deadline",
            "riziko", "odporucat", "odporucam", "lehota", "vypoved", "pisomne", "upozornenie",
        }
        risk_awareness = 1.0 if (risk_markers & final_tokens) else 0.45

        return [
            CriterionScore(
                name="legal_accuracy",
                score=round(legal_overlap * 100, 2),
                rationale="Computed from overlap between expected legal points and final answer.",
            ),
            CriterionScore(
                name="coverage",
                score=round(coverage_overlap * 100, 2),
                rationale="Computed from overlap between expected legal points and transcript.",
            ),
            CriterionScore(
                name="clarity",
                score=round(clarity * 100, 2),
                rationale="Shorter, well-bounded conclusions receive higher clarity.",
            ),
            CriterionScore(
                name="risk_awareness",
                score=round(risk_awareness * 100, 2),
                rationale="Checks whether caveats or next-step guidance is present.",
            ),
        ]

    def _llm_scores(
        self,
        fallback_scores: Sequence[CriterionScore],
        transcript: str,
        inputs: ValidatorInputs,
        final_result: str,
    ) -> tuple[list[CriterionScore], str]:
        if self.llm is None:
            return [], ""

        criteria_text = "\n".join(f"- {c.name}: {c.description}" for c in self.criteria)
        fallback_json = json.dumps([s.__dict__ for s in fallback_scores], ensure_ascii=False)
        prompt = (
            "Evaluate legal response quality and return strict JSON with this schema: "
            '{"scores":[{"name":"...","score":0-100,"rationale":"..."}],"summary":"..."}.\n'
            f"Country: {inputs.country}\n"
            f"User question: {inputs.question}\n"
            f"Expected legal points: {list(inputs.expected_points)}\n"
            f"Criteria:\n{criteria_text}\n"
            f"Fallback heuristic scores: {fallback_json}\n"
            f"Transcript:\n{transcript[:4000]}\n"
            f"Final result:\n{final_result[:2000]}"
        )
        from ..schemas import Message

        raw = self.llm.complete(
            agent_name="AIAgentsValidator",
            system_prompt="You are an objective legal QA evaluator. Return only strict JSON.",
            conversation=[Message(role="user", agent_name="ValidatorInput", content=prompt)],
            documents=[],
        )
        # LLM clients may not support ad-hoc prompt through conversation in this project; keep
        # fallback behavior deterministic by ignoring invalid payloads.
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [], _build_summary(fallback_scores)

        raw_scores = parsed.get("scores")
        if not isinstance(raw_scores, list):
            return [], _build_summary(fallback_scores)

        scores: list[CriterionScore] = []
        for item in raw_scores:
            if not isinstance(item, dict):
                continue
            try:
                scores.append(
                    CriterionScore(
                        name=str(item["name"]),
                        score=float(item["score"]),
                        rationale=str(item.get("rationale", "")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

        if not scores:
            return [], _build_summary(fallback_scores)

        return scores, str(parsed.get("summary", _build_summary(scores)))


def _extract_transcript(payload: dict[str, Any]) -> str:
    qa_pairs = payload.get("qaPairs")
    if isinstance(qa_pairs, list) and qa_pairs:
        chunks: list[str] = []
        for pair in qa_pairs:
            if not isinstance(pair, dict):
                continue
            q = str(pair.get("question", "")).strip()
            a = str(pair.get("answer", "")).strip()
            if q:
                chunks.append(f"Q: {q}")
            if a:
                chunks.append(f"A: {a}")
        return "\n".join(chunks)

    messages = payload.get("messages")
    if isinstance(messages, list):
        return "\n".join(
            f"{str(msg.get('role', 'unknown')).upper()}: {str(msg.get('content', ''))}"
            for msg in messages
            if isinstance(msg, dict)
        )

    return ""


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[^\W\d_]{3,}", text, flags=re.UNICODE)}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, numerator / denominator)


def _weighted_accuracy(scores: Sequence[CriterionScore], criteria: Sequence[EvaluationCriterion]) -> float:
    weight_map = {item.name: item.weight for item in criteria}
    total_weight = sum(weight_map.values())
    if total_weight <= 0:
        return 0.0

    weighted = 0.0
    for score in scores:
        weighted += max(0.0, min(100.0, score.score)) * weight_map.get(score.name, 0.0)
    return round(weighted / total_weight, 2)


def _build_summary(scores: Sequence[CriterionScore]) -> str:
    if not scores:
        return "No scores were produced."
    best = max(scores, key=lambda item: item.score)
    weakest = min(scores, key=lambda item: item.score)
    return (
        f"Strongest axis: {best.name} ({best.score:.1f}). "
        f"Needs improvement: {weakest.name} ({weakest.score:.1f})."
    )


def _contract_similarity(final_contract: str, reference_contracts: Sequence[str]) -> float:
    final_tokens = _tokens(final_contract)
    if not final_tokens:
        return 0.0

    required_sections = {
        "zmluvne", "strany", "predmet", "najmu", "doba", "najomne", "kaucia", "ukoncenie", "vypovedna", "pisomne"
    }
    section_coverage = _safe_ratio(len(final_tokens & required_sections), len(required_sections))

    references = list(reference_contracts)
    if not references:
        references = [
            "zmluvne strany predmet najmu doba najmu najomne splatnost kaucia vypovedna lehota podpis",
        ]

    best_f1 = 0.0
    for sample in references:
        sample_tokens = _tokens(sample)
        if not sample_tokens:
            continue
        overlap = len(final_tokens & sample_tokens)
        precision = _safe_ratio(overlap, len(final_tokens))
        recall = _safe_ratio(overlap, len(sample_tokens))
        f1 = 0.0 if (precision + recall) == 0 else (2 * precision * recall) / (precision + recall)
        best_f1 = max(best_f1, f1)

    combined = 0.6 * section_coverage + 0.4 * best_f1
    return round(combined * 100, 2)


def _human_likeness(transcript: str) -> float:
    lowered = transcript.lower()
    if not lowered.strip():
        return 0.0

    question_mark_count = transcript.count("?")
    qa_markers = sum(1 for marker in ("q:", "a:", "user:", "assistant:") if marker in lowered)
    empathy_markers = sum(
        1
        for marker in ("rozumiem", "ďakujem", "dakujem", "prosím", "prosim", "i understand", "thank you")
        if marker in lowered
    )
    legal_markers = sum(
        1
        for marker in ("zmluva", "nájom", "najom", "výpoveď", "vypoved", "lehota", "jurisdikcia", "dôkaz")
        if marker in lowered
    )

    score = min(1.0, 0.2 + question_mark_count * 0.03 + qa_markers * 0.08 + empathy_markers * 0.05 + legal_markers * 0.05)
    return round(score * 100, 2)
