"""Explainable, deterministic job-to-profile matching heuristics."""

import re

from app.db.models import CandidateProfile, Job
from app.schemas import JobMatchResult

SKILL_PATTERNS: dict[str, tuple[str, ...]] = {
    "Python": (r"python",),
    "C++": (r"c\+\+", r"cpp", r"c plus plus"),
    "C#": (r"c#", r"c sharp"),
    "Java": (r"java",),
    "JavaScript": (r"javascript", r"js"),
    "TypeScript": (r"typescript",),
    "SQL": (r"sql",),
    "MySQL": (r"mysql",),
    "PostgreSQL": (r"postgresql", r"postgres"),
    "Git": (r"git",),
    "Linux": (r"linux",),
    "Docker": (r"docker",),
    "AWS": (r"aws", r"amazon web services"),
    "Azure": (r"microsoft azure", r"azure"),
    "Google Cloud": (r"google cloud", r"gcp"),
    "Kubernetes": (r"kubernetes", r"k8s"),
    "React": (r"react", r"react\.js"),
    "FastAPI": (r"fastapi",),
    ".NET": (r"\.net", r"dotnet"),
    "Node.js": (r"node\.js", r"nodejs"),
    "REST APIs": (r"rest api", r"restful api"),
    "CI/CD": (r"ci/cd", r"continuous integration", r"continuous delivery"),
    "Automation": (r"automation", r"automated testing"),
    "Data analysis": (r"data analysis", r"data analytics", r"data analyst"),
    "Data processing": (r"data processing", r"data pipeline", r"etl"),
    "Video processing": (r"video processing", r"video analytics"),
    "Computer vision": (r"computer vision", r"image processing"),
    "Underwater robotics": (r"underwater robotics", r"remotely operated vehicle", r"\brov\b"),
    "Robotics": (r"robotics", r"robotic systems"),
    "Machine learning": (r"machine learning", r"\bml\b"),
    "Power BI": (r"power bi",),
    "Excel": (r"microsoft excel", r"\bexcel\b"),
    "Networking": (r"networking", r"computer networks"),
    "Active Directory": (r"active directory",),
    "IT support": (r"it support", r"technical support", r"help ?desk"),
    "Testing": (r"software testing", r"test automation", r"pytest", r"unit testing"),
}

TECH_ROLE_TERMS = (
    "software",
    "developer",
    "development",
    "programmer",
    "programming",
    "technology",
    "technical",
    "information technology",
    "it support",
    "data analyst",
    "data analysis",
    "automation",
    "robotics",
    "cybersecurity",
    "cyber security",
    "devops",
    "systems engineer",
    "network engineer",
    "qa engineer",
    "test engineer",
)
JUNIOR_TERMS = ("graduate", "junior", "entry level", "entry-level", "intern", "trainee")
SENIOR_TERMS = ("senior", "lead", "principal", "staff engineer", "manager")


def _has_pattern(text: str, pattern: str) -> bool:
    return re.search(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])", text, re.IGNORECASE) is not None


def _skills_in(text: str) -> set[str]:
    return {
        skill
        for skill, patterns in SKILL_PATTERNS.items()
        if any(_has_pattern(text, pattern) for pattern in patterns)
    }


def _extra_profile_skills(profile: CandidateProfile) -> set[str]:
    """Keep user-added skills matchable even when absent from the built-in catalog."""
    known = set(SKILL_PATTERNS)
    result = set()
    for raw_skill in profile.skills or []:
        skill = raw_skill.strip()
        if not skill:
            continue
        canonical = next(
            (
                name
                for name, patterns in SKILL_PATTERNS.items()
                if name.casefold() == skill.casefold()
                or any(_has_pattern(skill, pattern) for pattern in patterns)
            ),
            None,
        )
        result.add(canonical or skill)
    result.update(
        _skills_in(" ".join((profile.education, profile.placement, profile.experience_summary)))
    )
    return result | {s for s in profile.skills or [] if s.strip() not in known}


def _required_years(text: str) -> int | None:
    range_match = re.search(r"\b(\d+)\s*(?:-|–|to)\s*(\d+)\s*(?:\+\s*)?(?:years?|yrs?)\b", text)
    if range_match:
        return int(range_match.group(1))
    plus_match = re.search(r"\b(\d+)\s*\+\s*(?:years?|yrs?)\b", text)
    if plus_match:
        return int(plus_match.group(1))
    minimum_match = re.search(
        r"\b(?:at least|minimum of|required)\s+(\d+)\s*(?:years?|yrs?)\b", text
    )
    if minimum_match:
        return int(minimum_match.group(1))
    years_match = re.search(
        r"\b(\d+)\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|work|industry)", text
    )
    return int(years_match.group(1)) if years_match else None


def analyze_job(job: Job, profile: CandidateProfile) -> JobMatchResult:
    """Score one listing out of 100 and return the evidence behind the score."""
    title = job.title or ""
    description = job.description or ""
    experience_text = job.experience_required or ""
    listing_text = " ".join((title, description, experience_text))
    listing_folded = listing_text.casefold()
    candidate_skills = _extra_profile_skills(profile)
    requested_skills = _skills_in(listing_text)
    matched = sorted(requested_skills & candidate_skills, key=str.casefold)
    missing = sorted(requested_skills - candidate_skills, key=str.casefold)

    if requested_skills:
        skill_points = round(50 * len(matched) / len(requested_skills))
        skill_reason = (
            f"Your profile matches {len(matched)} of {len(requested_skills)} recognized "
            "technical skills in the listing."
        )
    else:
        skill_points = 25
        skill_reason = (
            "The listing has too little recognizable skill detail for a strong comparison."
        )

    years = _required_years(" ".join((experience_text, description)))
    experience_flags: list[str] = []
    if years is not None:
        if years <= 2:
            experience_points = 25
            experience_reason = (
                f"The stated experience requirement ({years} years) is within your 0–2-year target."
            )
        else:
            experience_points = max(0, 25 - 8 * (years - 2))
            experience_flags.append(
                f"The listing asks for at least {years} years of experience, "
                "above your 0–2-year target."
            )
            experience_reason = (
                f"The stated {years}-year experience requirement reduces the fit score."
            )
    elif any(term in title.casefold() for term in JUNIOR_TERMS):
        experience_points = 25
        experience_reason = (
            "The title identifies this as a graduate, junior, intern, trainee, or entry-level role."
        )
    elif any(term in title.casefold() for term in SENIOR_TERMS):
        experience_points = 4
        experience_flags.append(
            "The title suggests a senior, lead, principal, or management level role."
        )
        experience_reason = (
            "The title suggests a level above the graduate/junior roles you are targeting."
        )
    else:
        experience_points = 17
        experience_reason = "The listing does not state a clear experience level."

    profile_education = (profile.education or "").casefold()
    higher_degree_requested = any(
        term in listing_folded for term in ("master's degree", "masters degree", "phd", "doctorate")
    )
    education_requested = any(
        term in listing_folded
        for term in (
            "bachelor",
            "bachelors",
            "degree",
            "computer science",
            "information technology",
        )
    )
    if higher_degree_requested and not any(
        term in profile_education for term in ("master", "phd", "doctorate")
    ):
        education_points = 2
        experience_flags.append(
            "The listing appears to require a postgraduate qualification not shown in your profile."
        )
        education_reason = "The requested postgraduate qualification is not listed in your profile."
    elif education_requested and any(
        term in profile_education
        for term in ("computer science", "information technology", "bachelor", "computing")
    ):
        education_points = 15
        education_reason = (
            "Your Computer Science degree aligns with the qualification or study area mentioned."
        )
    elif education_requested:
        education_points = 7
        education_reason = (
            "The listing mentions a qualification, but your profile does not clearly "
            "show the same requirement."
        )
    else:
        education_points = 12
        education_reason = (
            "No specific degree requirement was found, so education fit is treated as neutral."
        )

    title_folded = title.casefold()
    has_tech_role = any(term in title_folded for term in TECH_ROLE_TERMS)
    if has_tech_role:
        role_points = 10
        role_reason = (
            "The title is within your software, IT, data, automation, or technology search area."
        )
    elif any(term in listing_folded for term in TECH_ROLE_TERMS):
        role_points = 6
        role_reason = (
            "The description contains technology work, though the title is not a clear match."
        )
    else:
        role_points = 0
        role_reason = "The listing does not clearly match your target technology roles."

    breakdown = {
        "technical_skills": skill_points,
        "experience_level": experience_points,
        "education": education_points,
        "role_area": role_points,
    }
    score = max(0, min(100, sum(breakdown.values())))
    reasons = [skill_reason, experience_reason, education_reason, role_reason]
    if matched:
        reasons.append("Skills already in your profile: " + ", ".join(matched) + ".")
    if missing:
        reasons.append("Potential skill gaps: " + ", ".join(missing) + ".")
    if not description.strip():
        reasons.append(
            "No job description was supplied, so this score relies mainly on the title "
            "and experience field."
        )
    explanation = f"{score}/100. " + " ".join(reasons)
    return JobMatchResult(
        score=score,
        explanation=explanation,
        reasons=reasons,
        score_breakdown=breakdown,
        matched_skills=matched,
        missing_skills=missing,
        experience_flags=experience_flags,
    )
