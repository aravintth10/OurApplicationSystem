"""
Honeypot detection for impossible or fraudulent candidate profiles.
"""

from datetime import date, datetime
from typing import Dict, Any


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def is_honeypot(candidate: Dict[str, Any]) -> tuple[bool, str]:
    """Scans profile details for impossible/fraudulent patterns."""
    today = date.today()
    profile = candidate.get("profile", {})
    career = candidate.get("career_history", [])
    skills = candidate.get("skills", [])
    signals = candidate.get("redrob_signals", {})

    yoe = profile.get("years_of_experience", 0) or 0

    # Total role duration should align with YoE
    total_months = sum(r.get("duration_months", 0) or 0 for r in career)
    if yoe > 3 and total_months > 0:
        career_years = total_months / 12
        if yoe > career_years * 1.8 + 2:
            return True, f"YoE ({yoe:.1f}y) grossly exceeds career timeline ({career_years:.1f}y)"

    # Check if a role duration exceeds calendar range
    for role in career:
        start = parse_date(role.get("start_date"))
        end = parse_date(role.get("end_date")) or today
        duration_months = role.get("duration_months", 0) or 0
        if start and duration_months > 0:
            actual_months = (end.year - start.year) * 12 + (end.month - start.month)
            if duration_months > actual_months + 2 and duration_months > 12:
                return True, (
                    f"Role at {role.get('company', '?')} claims {duration_months}mo "
                    f"but dates only span {actual_months}mo"
                )

    # Zero duration expert skills
    expert_zero_duration = [
        s["name"] for s in skills
        if s.get("proficiency") == "expert" and s.get("duration_months", 1) == 0
    ]
    if len(expert_zero_duration) >= 2:
        return True, f"Expert in {len(expert_zero_duration)} skills with 0 months duration"

    # Too many expert skills
    expert_skills = [s for s in skills if s.get("proficiency") == "expert"]
    if len(expert_skills) >= 9:
        return True, f"Claims expert in {len(expert_skills)} skills (unrealistic)"

    # Impossible perfect behavioral signals
    rr = signals.get("recruiter_response_rate", 0)
    icr = signals.get("interview_completion_rate", 0)
    oar = signals.get("offer_acceptance_rate", -1)
    completeness = signals.get("profile_completeness_score", 0)
    if rr == 1.0 and icr == 1.0 and oar == 1.0 and completeness == 100:
        return True, "Impossible perfect behavioral signals"

    # Future signup date
    signup = parse_date(signals.get("signup_date"))
    if signup and signup > today:
        return True, f"Signup date {signup} is in the future"

    # Activity before signup
    last_active = parse_date(signals.get("last_active_date"))
    if signup and last_active and last_active < signup:
        return True, f"Last active ({last_active}) before signup ({signup})"

    # Overlapping full-time roles
    if len(career) >= 2:
        overlaps = 0
        for i in range(len(career)):
            r1 = career[i]
            s1 = parse_date(r1.get("start_date"))
            e1 = parse_date(r1.get("end_date")) or today
            for j in range(i + 1, len(career)):
                r2 = career[j]
                s2 = parse_date(r2.get("start_date"))
                e2 = parse_date(r2.get("end_date")) or today
                if s1 and s2 and e1 and e2:
                    overlap_start = max(s1, s2)
                    overlap_end = min(e1, e2)
                    if overlap_start < overlap_end:
                        overlap_months = (
                            (overlap_end.year - overlap_start.year) * 12
                            + (overlap_end.month - overlap_start.month)
                        )
                        if overlap_months > 12:
                            overlaps += 1
        if overlaps >= 2:
            return True, f"Multiple severely overlapping full-time roles ({overlaps} pairs)"

    # Unreasonable career start year
    if career:
        oldest_start = min(
            (parse_date(r.get("start_date")) for r in career if r.get("start_date")),
            default=None,
        )
        if oldest_start:
            implied_birth_year = oldest_start.year - 18
            if implied_birth_year < 1950 or implied_birth_year > 2005:
                return True, f"Career start implies implausible birth year {implied_birth_year}"

    # Experience exceeds time since graduation
    education = candidate.get("education", [])
    if education and yoe > 2:
        latest_grad = max(
            (e.get("end_year", 0) for e in education if e.get("end_year")),
            default=None,
        )
        if latest_grad:
            max_possible_yoe = today.year - latest_grad + 1
            if yoe > max_possible_yoe + 3:
                return True, (
                    f"YoE ({yoe:.1f}y) exceeds max possible since graduation "
                    f"({latest_grad}, max ~{max_possible_yoe}y)"
                )

    return False, ""
