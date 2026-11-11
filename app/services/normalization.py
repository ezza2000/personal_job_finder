"""Text normalization and explainable duplicate candidate matching."""

import re
from difflib import SequenceMatcher


def normalize_text(value: str | None) -> str:
    """Lowercase and collapse punctuation/whitespace for comparison keys."""
    if not value:
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def compare_jobs(
    title_a: str, company_a: str, title_b: str, company_b: str
) -> tuple[int, list[str]] | None:
    """Return a possible duplicate score and reasons; never decides to merge records."""
    title_a_norm, title_b_norm = normalize_text(title_a), normalize_text(title_b)
    company_a_norm, company_b_norm = normalize_text(company_a), normalize_text(company_b)
    title_score = SequenceMatcher(None, title_a_norm, title_b_norm).ratio()
    company_score = SequenceMatcher(None, company_a_norm, company_b_norm).ratio()

    reasons: list[str] = []
    if company_score >= 0.88:
        reasons.append("Company names are very similar")
    if title_score >= 0.78:
        reasons.append("Job titles are very similar")
    if company_score >= 0.88 and title_score >= 0.68:
        return round(100 * (0.55 * company_score + 0.45 * title_score)), reasons
    if company_score == 1 and title_score == 1:
        return 100, ["Company and job title match exactly"]
    return None
