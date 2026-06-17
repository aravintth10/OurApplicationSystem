"""
Scoring engine for candidate profiles matching the Senior AI Engineer JD.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from skills_config import (
    TIER_A_SKILLS,
    TIER_B_SKILLS,
    TIER_C_SKILLS,
    TIER_WEIGHTS,
    PROFICIENCY_MULT,
    TITLE_SCORES,
    SUMMARY_KEYWORDS,
    INDUSTRY_SCORES,
    INDIA_TIER1_CITIES,
    INDIA_TIER2_CITIES,
    SALARY_MIN_EXPECTED,
    SALARY_MAX_BUDGET,
    PRODUCTION_ML_SIGNALS,
    RESEARCH_ANTI_SIGNALS,
)

COMPONENT_WEIGHTS = {
    "career":   0.50,
    "title":    0.23,
    "skill":    0.20,
    "location": 0.05,
    "edu":      0.02,
}

MAX_RAW_SKILL = 25.0


def _lc(text: str) -> str:
    return text.lower()


def _today() -> date:
    return date.today()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


def _lerp(a: float, b: float, t: float) -> float:
    t = _clamp(t)
    return a + (b - a) * t


def _skill_tier(skill_name_lc: str) -> str | None:
    for keyword in TIER_A_SKILLS:
        if keyword in skill_name_lc:
            return "A"
    for keyword in TIER_B_SKILLS:
        if keyword in skill_name_lc:
            return "B"
    for keyword in TIER_C_SKILLS:
        if keyword in skill_name_lc:
            return "C"
    return None


def score_skills(candidate: Dict[str, Any]) -> Tuple[float, Dict]:
    skills: List[Dict] = candidate.get("skills", [])
    signals: Dict = candidate.get("redrob_signals", {})
    assessment_scores: Dict = signals.get("skill_assessment_scores", {})

    existing_skills = {}
    for s in skills:
        name_lc = _lc(s.get("name", ""))
        existing_skills[name_lc] = s

    # Extract skill keywords from experience descriptions and bios
    extracted = {}
    career = candidate.get("career_history", [])
    profile = candidate.get("profile", {})
    summary = _lc(profile.get("summary", ""))
    headline = _lc(profile.get("headline", ""))
    
    for r in career:
        desc = _lc(r.get("description", ""))
        title = _lc(r.get("title", ""))
        duration = r.get("duration_months", 0) or 0
        role_text = desc + " " + title
        
        for kw in TIER_A_SKILLS:
            if kw in role_text:
                if kw not in extracted or duration > extracted[kw]["duration_months"]:
                    extracted[kw] = {"proficiency": "intermediate", "duration_months": duration, "tier": "A"}
        for kw in TIER_B_SKILLS:
            if kw in role_text:
                if kw not in extracted or duration > extracted[kw]["duration_months"]:
                    extracted[kw] = {"proficiency": "intermediate", "duration_months": duration, "tier": "B"}
        for kw in TIER_C_SKILLS:
            if kw in role_text:
                if kw not in extracted or duration > extracted[kw]["duration_months"]:
                    extracted[kw] = {"proficiency": "intermediate", "duration_months": duration, "tier": "C"}

    for kw in TIER_A_SKILLS:
        if kw in summary or kw in headline:
            if kw not in extracted:
                extracted[kw] = {"proficiency": "intermediate", "duration_months": 0, "tier": "A"}
    for kw in TIER_B_SKILLS:
        if kw in summary or kw in headline:
            if kw not in extracted:
                extracted[kw] = {"proficiency": "intermediate", "duration_months": 0, "tier": "B"}
    for kw in TIER_C_SKILLS:
        if kw in summary or kw in headline:
            if kw not in extracted:
                extracted[kw] = {"proficiency": "intermediate", "duration_months": 0, "tier": "C"}

    # Combine and deduplicate
    combined_skills = list(skills)
    for name, s_info in extracted.items():
        already_present = False
        for existing_name in existing_skills:
            if name in existing_name or existing_name in name:
                already_present = True
                break
        if not already_present:
            combined_skills.append({
                "name": name,
                "proficiency": s_info["proficiency"],
                "endorsements": 5,
                "duration_months": s_info["duration_months"]
            })

    raw = 0.0
    tier_counts = {"A": 0, "B": 0, "C": 0}
    matched_skills = []

    for skill in combined_skills:
        name_lc = _lc(skill.get("name", ""))
        tier = _skill_tier(name_lc)
        if tier is None:
            continue

        proficiency = skill.get("proficiency", "intermediate")
        prof_mult = PROFICIENCY_MULT.get(proficiency, 1.0)

        endorsements = skill.get("endorsements", 0) or 0
        endorse_mult = 1.0 + min(endorsements / 100, 0.3)

        duration_months = skill.get("duration_months", 0) or 0
        dur_mult = 1.0
        if duration_months >= 36:
            dur_mult = 1.25
        elif duration_months >= 24:
            dur_mult = 1.15
        elif duration_months >= 12:
            dur_mult = 1.05
        elif duration_months == 0 and proficiency in ("advanced", "expert"):
            dur_mult = 0.7

        assess_bonus = 0.0
        for assess_name, assess_score in assessment_scores.items():
            if _lc(assess_name) in name_lc or name_lc in _lc(assess_name):
                assess_bonus = (assess_score / 100) * 0.5
                break

        tier_weight = TIER_WEIGHTS[tier]
        contribution = tier_weight * prof_mult * endorse_mult * dur_mult + assess_bonus

        raw += contribution
        tier_counts[tier] += 1
        matched_skills.append(name_lc)

    if tier_counts["A"] >= 5:
        raw *= 1.15
    elif tier_counts["A"] >= 3:
        raw *= 1.08

    total_ai = tier_counts["A"] + tier_counts["B"]
    if total_ai == 0:
        raw *= 0.3

    normalised = _clamp(raw / MAX_RAW_SKILL)
    return normalised, {
        "tier_A": tier_counts["A"],
        "tier_B": tier_counts["B"],
        "tier_C": tier_counts["C"],
        "matched": matched_skills[:8],
    }


def score_title(candidate: Dict[str, Any]) -> Tuple[float, str]:
    profile = candidate.get("profile", {})
    title = _lc(profile.get("current_title", ""))
    headline = _lc(profile.get("headline", ""))
    summary = _lc(profile.get("summary", ""))

    title_score = 0.0
    for kw, sc in TITLE_SCORES.items():
        if kw in title:
            title_score = max(title_score, sc)

    # Non-technical title penalty
    non_tech_keywords = ["marketing", "hr ", "hr manager", "accountant", "sales", "customer support", "mechanical", "civil", "operations manager", "graphic designer", "writer"]
    is_non_tech = any(kw in title for kw in non_tech_keywords)
    has_tech_fallback = any(kw in title for kw in ["engineer", "scientist", "developer", "programmer", "architect", "tech", "data", "ml", "ai", "nlp"])
    if is_non_tech and not has_tech_fallback:
        title_score = 0.01

    headline_score = 0.0
    for kw, sc in TITLE_SCORES.items():
        if kw in headline:
            headline_score = max(headline_score, sc * 0.9)

    summary_raw = 0.0
    for kw, weight in SUMMARY_KEYWORDS.items():
        count = summary.count(kw) + headline.count(kw)
        if count > 0:
            summary_raw += weight * min(count, 3)

    summary_score = _clamp(summary_raw / 20.0) * 0.4

    # Production vs research check
    prod_hits = sum(1 for sig in PRODUCTION_ML_SIGNALS if sig in summary)
    prod_bonus = _clamp(prod_hits / 8.0) * 0.1

    research_penalty = sum(1 for sig in RESEARCH_ANTI_SIGNALS if sig in summary) * 0.05

    combined = (
        max(title_score, headline_score) * 0.5
        + summary_score
        + prod_bonus
        - research_penalty
    )

    return _clamp(combined), title


def score_career(candidate: Dict[str, Any]) -> Tuple[float, str]:
    profile = candidate.get("profile", {})
    career: List[Dict] = candidate.get("career_history", [])
    yoe = profile.get("years_of_experience", 0) or 0

    # Non-linear scaling for experience
    if yoe < 2:
        yoe_score = 0.1
    elif yoe < 4:
        yoe_score = _lerp(0.25, 0.65, (yoe - 2) / 2)
    elif yoe < 5:
        yoe_score = _lerp(0.65, 0.85, (yoe - 4))
    elif yoe <= 9:
        yoe_score = _lerp(0.85, 1.0, (yoe - 5) / 4)
    elif yoe <= 13:
        yoe_score = _lerp(1.0, 0.80, (yoe - 9) / 4)
    else:
        yoe_score = _lerp(0.80, 0.60, min((yoe - 13) / 7, 1))

    industry_scores = []
    startup_bonus = 0.0
    
    retrieval_roles = 0
    ranking_roles = 0
    rag_llm_roles = 0
    evaluation_roles = 0

    for role in career:
        industry_lc = _lc(role.get("industry", ""))
        role_score = 0.0
        for ind, sc in INDUSTRY_SCORES.items():
            if ind in industry_lc:
                role_score = max(role_score, sc)
        if role_score == 0.0:
            role_score = 0.35
        industry_scores.append(role_score)

        company_size = role.get("company_size", "")
        if company_size in ("1-10", "11-50", "51-200"):
            startup_bonus = max(startup_bonus, 0.15)
        elif company_size in ("201-500",):
            startup_bonus = max(startup_bonus, 0.08)

        desc = _lc(role.get("description", ""))
        title = _lc(role.get("title", ""))
        role_text = desc + " " + title

        # System building criteria check
        if any(kw in role_text for kw in [
            "embeddings", "embedding", "sentence-transformers", "sentence transformers",
            "vector search", "vector database", "vector db", "vectordb", "milvus", "pinecone",
            "weaviate", "qdrant", "faiss", "opensearch", "elasticsearch", "dense retrieval",
            "sparse retrieval", "hybrid search", "indexing algorithms", "search engine",
            "information retrieval", "ir system"
        ]):
            retrieval_roles += 1

        if any(kw in role_text for kw in [
            "ranking", "learning to rank", "reranking", "re-ranking", "ndcg", "mrr", "map",
            "precision at k", "precision@k", "recall at k", "recall@k",
            "collaborative filtering", "matrix factorization", "recommendation system", "recommender"
        ]):
            ranking_roles += 1

        if any(kw in role_text for kw in [
            "rag", "retrieval augmented generation", "retrieval-augmented",
            "llm", "large language model", "fine-tuning", "fine tuning", "finetuning",
            "lora", "qlora", "peft"
        ]):
            rag_llm_roles += 1

        if any(kw in role_text for kw in [
            "ndcg", "mrr", "map", "offline evaluation", "offline benchmark", "offline eval",
            "evaluation framework", "a/b test", "a/b testing", "online evaluation", "experimentation framework"
        ]):
            evaluation_roles += 1

    system_building_score = 0.0
    if retrieval_roles > 0:
        system_building_score += 0.35
    if ranking_roles > 0:
        system_building_score += 0.35
    if rag_llm_roles > 0:
        system_building_score += 0.15
    if evaluation_roles > 0:
        system_building_score += 0.15

    if retrieval_roles >= 2:
        system_building_score += 0.1
    if ranking_roles >= 2:
        system_building_score += 0.1

    system_building_score = _clamp(system_building_score)
    avg_industry = sum(industry_scores) / len(industry_scores) if industry_scores else 0.35

    senior_count = sum(
        1 for r in career
        if any(t in _lc(r.get("title", "")) for t in ["senior", "lead", "staff", "principal", "head", "founding"])
    )
    senior_bonus = min(senior_count * 0.08, 0.20)

    career_raw = (
        yoe_score * 0.25
        + system_building_score * 0.45
        + avg_industry * 0.15
        + startup_bonus * 0.08
        + senior_bonus * 0.07
    )

    # Apply penalties and adjustments
    all_desc = " ".join([_lc(r.get("description", "")) for r in career]) + " " + _lc(profile.get("summary", ""))
    
    # Penalty for services/consulting only
    companies = [r.get("company", "") for r in career if r.get("company")]
    if companies:
        consulting_firms = {
            "tcs", "tata consultancy", "infosys", "wipro", "accenture",
            "cognizant", "capgemini", "tech mahindra", "hcl", "l&t",
            "mindtree", "deloitte", "ey", "pwc", "kpmg", "services"
        }
        only_consulting = True
        for company in companies:
            comp_lc = _lc(company)
            is_consulting = any(firm in comp_lc for firm in consulting_firms)
            if not is_consulting:
                only_consulting = False
                break
        if only_consulting:
            career_raw *= 0.15

    # Penalty for API wrapper projects lacking depth
    has_wrapper = any(w in all_desc for w in ["langchain", "streamlit", "gradio", "openai api", "chatgpt api", "wrapper"])
    has_low_level = any(w in all_desc for w in ["pytorch", "tensorflow", "scikit-learn", "sklearn", "numpy", "custom", "pipeline", "infra", "database", "deploy", "docker", "kubernetes", "indexing", "model-serving", "serving", "from scratch", "from-scratch", "optimized", "scale"])
    if has_wrapper and not has_low_level:
        career_raw *= 0.30

    # Penalty for job hopping
    num_companies = len(set(_lc(r.get("company", "")) for r in career if r.get("company")))
    if num_companies >= 3 and yoe > 0:
        avg_duration = yoe / num_companies
        if avg_duration < 1.5:
            career_raw *= 0.60

    # Penalty for academic-only profiles
    has_research = any(w in all_desc for w in ["phd thesis", "dissertation", "arxiv", "publication", "academic", "journal", "lab", "research assistant", "postdoc"])
    has_production = any(w in all_desc for w in ["production", "deployed", "kubernetes", "docker", "real-time", "scale", "api", "serving"])
    if has_research and not has_production:
        career_raw *= 0.40

    # Penalty for pure vision/speech without retrieval focus
    has_cv_speech = any(w in all_desc for w in ["computer vision", "speech", "audio", "robotics", "image classification", "object detection", "yolo", "cnn", "image", "video", "speech recognition", "tts", "speech-to-text"])
    has_nlp_ir = any(w in all_desc for w in ["nlp", "text", "search", "retrieval", "ranking", "recommender", "embeddings", "rag", "information retrieval", "natural language", "transformer", "bert", "gpt", "llm", "vector database", "opensearch", "elasticsearch", "indexing"])
    if has_cv_speech and not has_nlp_ir:
        career_raw *= 0.40

    career_note = f"{yoe:.1f}y exp; {len(career)} roles"
    return _clamp(career_raw), career_note


def score_education(candidate: Dict[str, Any]) -> float:
    education = candidate.get("education", [])
    if not education:
        return 0.30

    TIER_SCORE = {"tier_1": 1.0, "tier_2": 0.75, "tier_3": 0.45, "tier_4": 0.25, "unknown": 0.35}
    RELEVANT_FIELDS = {
        "computer science", "cs", "software", "artificial intelligence", "machine learning",
        "data science", "statistics", "mathematics", "electrical engineering",
        "electronics", "information technology", "it",
    }
    ADVANCED_DEGREES = {"m.tech", "mtech", "m.s.", "ms", "m.e.", "me", "m.sc", "msc", "phd", "ph.d"}

    best_tier_score = 0.0
    field_bonus = 0.0
    degree_bonus = 0.0

    for edu in education:
        tier = edu.get("tier", "unknown")
        tier_sc = TIER_SCORE.get(tier, 0.35)
        best_tier_score = max(best_tier_score, tier_sc)

        field_lc = _lc(edu.get("field_of_study", ""))
        if any(f in field_lc for f in RELEVANT_FIELDS):
            field_bonus = max(field_bonus, 0.15)

        degree_lc = _lc(edu.get("degree", ""))
        if any(d in degree_lc for d in ADVANCED_DEGREES):
            degree_bonus = max(degree_bonus, 0.10)

    return _clamp(best_tier_score * 0.75 + field_bonus + degree_bonus)


def score_location(candidate: Dict[str, Any]) -> float:
    profile = candidate.get("profile", {})
    country = _lc(profile.get("country", ""))
    location = _lc(profile.get("location", ""))
    signals = candidate.get("redrob_signals", {})
    relocate = signals.get("willing_to_relocate", False)

    in_india = "india" in country
    in_tier1 = any(city in location for city in INDIA_TIER1_CITIES)
    in_tier2 = any(city in location for city in INDIA_TIER2_CITIES)

    if in_india and in_tier1:
        return 1.0
    elif in_india and in_tier2:
        return 0.80
    elif in_india:
        return 0.70
    elif relocate:
        return 0.45
    else:
        return 0.10


def engagement_multiplier(candidate: Dict[str, Any]) -> Tuple[float, str]:
    signals = candidate.get("redrob_signals", {})
    today = _today()

    mult = 1.0
    notes = []

    last_active = _parse_date(signals.get("last_active_date"))
    if last_active:
        days_inactive = (today - last_active).days
        if days_inactive > 365:
            mult *= 0.25
            notes.append("inactive >1yr")
        elif days_inactive > 180:
            mult *= 0.45
            notes.append("inactive >6mo")
        elif days_inactive > 90:
            mult *= 0.65
            notes.append("inactive >3mo")
        elif days_inactive > 30:
            mult *= 0.85

    open_to_work = signals.get("open_to_work_flag", False)
    if not open_to_work:
        mult *= 0.55
        notes.append("not open to work")

    rr = signals.get("recruiter_response_rate", 0.5)
    if rr < 0.05:
        mult *= 0.50
        notes.append(f"response_rate={rr:.2f}")
    elif rr < 0.15:
        mult *= 0.70
    elif rr < 0.30:
        mult *= 0.85
    else:
        mult *= _lerp(0.90, 1.05, (rr - 0.30) / 0.70)

    icr = signals.get("interview_completion_rate", 0.5)
    if icr < 0.3:
        mult *= 0.70
        notes.append(f"interview_rate={icr:.2f}")
    elif icr < 0.6:
        mult *= 0.88
    else:
        mult *= _lerp(0.95, 1.02, (icr - 0.6) / 0.4)

    oar = signals.get("offer_acceptance_rate", -1)
    if oar != -1:
        if oar < 0.2:
            mult *= 0.80
        elif oar > 0.8:
            mult *= 1.02

    notice = signals.get("notice_period_days", 60)
    if notice > 120:
        mult *= 0.82
        notes.append(f"notice={notice}d")
    elif notice <= 15:
        mult *= 1.03
    elif notice <= 30:
        mult *= 1.01

    work_mode = signals.get("preferred_work_mode", "flexible")
    if work_mode == "flexible" or work_mode == "hybrid":
        pass
    elif work_mode == "onsite":
        mult *= 0.97
    elif work_mode == "remote":
        mult *= 0.88

    github = signals.get("github_activity_score", -1)
    if github == -1:
        mult *= 0.92
    elif github > 75:
        mult *= 1.08
    elif github > 50:
        mult *= 1.04
    elif github < 10:
        mult *= 0.95

    completeness = signals.get("profile_completeness_score", 70)
    if completeness < 40:
        mult *= 0.85
    elif completeness > 85:
        mult *= 1.02

    salary = signals.get("expected_salary_range_inr_lpa", {})
    sal_min = salary.get("min", 0) or 0
    sal_max = salary.get("max", 0) or 0
    if sal_min > SALARY_MAX_BUDGET:
        mult *= 0.70
        notes.append(f"salary_min={sal_min}L (over budget)")
    elif sal_max < SALARY_MIN_EXPECTED and sal_max > 0:
        mult *= 0.85

    verified_bonus = 0.0
    if signals.get("verified_email"):
        verified_bonus += 0.01
    if signals.get("verified_phone"):
        verified_bonus += 0.01
    if signals.get("linkedin_connected"):
        verified_bonus += 0.01
    mult = min(mult + verified_bonus, 1.15)

    search_30d = signals.get("search_appearance_30d", 0) or 0
    saved_30d = signals.get("saved_by_recruiters_30d", 0) or 0
    if saved_30d >= 3:
        mult = min(mult * 1.04, 1.15)
    if search_30d >= 20:
        mult = min(mult * 1.02, 1.15)

    note_str = "; ".join(notes) if notes else "good engagement"
    return _clamp(mult, 0.10, 1.15), note_str


def score_candidate(candidate: Dict[str, Any]) -> Tuple[float, str]:
    skill_sc, skill_detail = score_skills(candidate)
    title_sc, title_note = score_title(candidate)
    career_sc, career_note = score_career(candidate)
    edu_sc = score_education(candidate)
    loc_sc = score_location(candidate)
    eng_mult, eng_note = engagement_multiplier(candidate)

    base = (
        skill_sc    * COMPONENT_WEIGHTS["skill"]
        + title_sc  * COMPONENT_WEIGHTS["title"]
        + career_sc * COMPONENT_WEIGHTS["career"]
        + edu_sc    * COMPONENT_WEIGHTS["edu"]
        + loc_sc    * COMPONENT_WEIGHTS["location"]
    )

    final = _clamp(base * eng_mult)

    profile = candidate.get("profile", {})
    yoe = profile.get("years_of_experience", 0) or 0
    current_title = profile.get("current_title", "")
    current_company = profile.get("current_company", "")
    location = profile.get("location", "")
    country = profile.get("country", "")
    loc_display = f"{location}, {country}" if location and country else location or country

    tier_a = skill_detail["tier_A"]
    top_skills = ", ".join(skill_detail["matched"][:4]) if skill_detail["matched"] else "—"

    signals = candidate.get("redrob_signals", {})
    rr = signals.get("recruiter_response_rate", 0)
    notice = signals.get("notice_period_days", 60)
    github = signals.get("github_activity_score", -1)
    github_str = f"GitHub {github:.0f}/100" if github >= 0 else "no GitHub"
    open_to_work = signals.get("open_to_work_flag", False)

    positives = []
    if open_to_work:
        positives.append("open to work")
    if signals.get("verified_email"):
        positives.append("verified email")
    saved = signals.get("saved_by_recruiters_30d", 0)
    if saved and saved > 0:
        positives.append(f"saved by {saved} recruiters")

    concerns = []
    if not open_to_work:
        concerns.append("not open to work")
    if github == -1:
        concerns.append("no GitHub")
    if rr < 0.3:
        concerns.append(f"low response rate ({rr:.0%})")

    positives_str = "; ".join(positives) if positives else ""
    concerns_str = "; ".join(concerns) if concerns else ""

    reasoning_parts = [
        f"{current_title} at {current_company}" if current_company else current_title,
        f"{yoe:.1f}y exp",
        f"{tier_a} core AI skills ({top_skills})",
        f"loc: {loc_display}",
        f"response rate {rr:.0%}",
        f"notice {notice}d",
        github_str,
    ]
    if positives_str:
        reasoning_parts.append(f"positives: {positives_str}")
    if concerns_str:
        reasoning_parts.append(f"concerns: {concerns_str}")

    reasoning = "; ".join(p for p in reasoning_parts if p)

    return round(final, 6), reasoning
