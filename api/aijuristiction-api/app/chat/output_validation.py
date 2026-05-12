from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class LawyerOutputUserProfile:
    has_full_name: bool
    has_address: bool


class AILawyerOutputMessageValidationAgent:
    """Deterministic guardrails for user-facing lawyer output."""

    def validate(
        self,
        *,
        content: str,
        user_profile: LawyerOutputUserProfile | None,
    ) -> str:
        if not content.strip():
            return content
        visible, technical_suffix = _split_technical_suffix(content)
        cleaned = self._validate_missing_information_section(
            visible=visible,
            user_profile=user_profile,
        )
        return f"{cleaned}{technical_suffix}"

    def _validate_missing_information_section(
        self,
        *,
        visible: str,
        user_profile: LawyerOutputUserProfile | None,
    ) -> str:
        if "**Chýbajúce informácie / dokumenty:**" not in visible:
            return visible
        lines = visible.splitlines()
        output: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if _canonicalize(line) != "chybajuce informacie / dokumenty:":
                output.append(line)
                index += 1
                continue

            section_lines: list[str] = [line]
            index += 1
            while index < len(lines) and not _is_markdown_section_heading(lines[index]):
                section_lines.append(lines[index])
                index += 1

            validated_section = self._validate_missing_information_lines(
                section_lines=section_lines,
                user_profile=user_profile,
            )
            output.extend(validated_section)
        return "\n".join(output).strip()

    def _validate_missing_information_lines(
        self,
        *,
        section_lines: list[str],
        user_profile: LawyerOutputUserProfile | None,
    ) -> list[str]:
        if not section_lines:
            return []
        profile_complete = bool(user_profile and user_profile.has_full_name and user_profile.has_address)
        validated: list[str] = [section_lines[0]]
        for line in section_lines[1:]:
            if not _mentions_user_name_and_address(line):
                validated.append(line)
                continue
            if profile_complete:
                continue
            missing_parts: list[str] = []
            if not user_profile or not user_profile.has_full_name:
                missing_parts.append("meno")
            if not user_profile or not user_profile.has_address:
                missing_parts.append("adresu")
            missing_text = " a ".join(missing_parts) if missing_parts else "údaje"
            validated.append(
                f"- Chýba {missing_text}; doplňte tieto údaje v Profile, aby sa nabudúce automaticky použili."
            )
        non_empty_items = [line for line in validated[1:] if line.strip()]
        if not non_empty_items:
            return []
        return validated


def _split_technical_suffix(content: str) -> tuple[str, str]:
    marker_match = re.search(r"\n\s*(?:\*\*)?CASE_UPDATE_JSON(?:\*\*)?\s*:", content, flags=re.IGNORECASE)
    if marker_match:
        return content[: marker_match.start()].rstrip(), content[marker_match.start() :]
    return content, ""


def _mentions_user_name_and_address(line: str) -> bool:
    normalized = _canonicalize(line)
    user_name_markers = ("vase meno", "vas meno", "meno a adresa", "meno prenajimatela")
    address_markers = ("adresa", "adresu")
    return any(marker in normalized for marker in user_name_markers) and any(
        marker in normalized for marker in address_markers
    )


def _is_markdown_section_heading(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("**") and stripped.endswith("**") and ":" in stripped


def _canonicalize(value: str) -> str:
    stripped = value.strip().strip("*").strip()
    stripped = re.sub(r"^[\-\*\s]+", "", stripped)
    normalized = unicodedata.normalize("NFKD", stripped.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()
