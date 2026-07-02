import json
import os
from datetime import datetime

base_dir = r"d:\OneDrive\Desktop\hack2skill\data\[PUB] India_runs_data_and_ai_challenge\India_runs_data_and_ai_challenge"
candidates_file = os.path.join(base_dir, "candidates.jsonl")

# Honeypots
honeypot_ids = set()
with open(candidates_file, "r", encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        cid = c["candidate_id"]
        profile = c.get("profile", {})
        skills = c.get("skills", [])
        history = c.get("career_history", [])
        is_hp = False
        for job in history:
            company = job.get("company", "")
            start_date_s = job.get("start_date")
            if start_date_s:
                try:
                    start_year = int(start_date_s.split("-")[0])
                    if "krutrim" in company.lower() and start_year < 2023:
                        is_hp = True
                    elif "sarvam" in company.lower() and start_year < 2023:
                        is_hp = True
                    elif "rephrase" in company.lower() and start_year < 2019:
                        is_hp = True
                except Exception:
                    pass
        zero_dur_skills = [sk["name"] for sk in skills if sk.get("proficiency") == "expert" and sk.get("duration_months", 0) == 0]
        if len(zero_dur_skills) >= 4:
            is_hp = True
        yoe = profile.get("years_of_experience", 0)
        earliest_job_year = 9999
        for job in history:
            start_s = job.get("start_date")
            if start_s:
                try:
                    yr = int(start_s.split("-")[0])
                    if yr < earliest_job_year:
                        earliest_job_year = yr
                except Exception:
                    pass
        if earliest_job_year != 9999:
            span = 2026 - earliest_job_year
            if yoe > span + 3:
                is_hp = True
        if is_hp:
            honeypot_ids.add(cid)

def get_experience_score(yoe):
    if 6 <= yoe <= 8:
        return 1.0
    elif 5 <= yoe < 6:
        return 0.8 + 0.2 * (yoe - 5)
    elif 8 < yoe <= 9:
        return 1.0 - 0.2 * (yoe - 8)
    elif 3 <= yoe < 5:
        return 0.2 + 0.3 * (yoe - 3)
    elif 9 < yoe <= 13:
        return 0.8 - 0.15 * (yoe - 9)
    else:
        return 0.05

def get_location_score(location, country, willing_to_relocate):
    loc_lower = str(location).lower()
    country_lower = str(country).lower()
    if "india" not in country_lower and country_lower != "":
        return 0.0  # Not in India
    noida_pune_cities = ["noida", "pune", "delhi", "gurgaon", "ncr", "ghaziabad", "faridabad"]
    other_welcome_cities = ["mumbai", "hyderabad", "navi mumbai"]
    if any(city in loc_lower for city in noida_pune_cities):
        return 1.0
    elif any(city in loc_lower for city in other_welcome_cities):
        return 0.9
    elif willing_to_relocate:
        return 0.8
    else:
        return 0.0  # In India but not in target cities and unwilling to relocate -> disqualified!

CONSULTING_FIRMS = {
    "infosys", "wipro", "tcs", "accenture", "cognizant", "capgemini",
    "tech mahindra", "mphasis", "hcl", "genpact", "mindtree", "tata consultancy"
}

def get_career_score(history):
    if not history:
        return 0.0, "No career history"
    total_jobs = len(history)
    consulting_jobs = 0
    ml_title_count = 0
    recent_is_ml = False
    for i, job in enumerate(history):
        company = str(job.get("company", "")).lower()
        title = str(job.get("title", "")).lower()
        desc = str(job.get("description", "")).lower()
        if any(firm in company for firm in CONSULTING_FIRMS):
            consulting_jobs += 1
        is_ml_job = False
        ml_keywords = ["ai", "ml", "machine learning", "nlp", "data scientist", "deep learning", 
                       "search", "retrieval", "ranking", "recommendation", "applied science", "applied scientist"]
        title_words = title.replace("/", " ").replace("-", " ").split()
        if any(kw in title_words or kw in title for kw in ml_keywords):
            is_ml_job = True
            ml_title_count += 1
            if i == 0:
                recent_is_ml = True
        if not is_ml_job:
            desc_keywords = ["embeddings", "vector database", "semantic search", "recommendation system", "fine-tuning"]
            if any(dk in desc for dk in desc_keywords):
                ml_title_count += 0.5
                if i == 0:
                    recent_is_ml = True
    consulting_ratio = consulting_jobs / total_jobs
    score = 0.0
    if recent_is_ml:
        score += 0.6
    elif ml_title_count > 0:
        score += 0.3
    score += min(0.4, (ml_title_count / total_jobs) * 0.4)
    if consulting_ratio == 1.0:
        score *= 0.1
    avg_duration = sum([job.get("duration_months", 0) for job in history]) / total_jobs
    if avg_duration < 18 and total_jobs > 1:
        score *= 0.7
    return score, f"ML jobs: {ml_title_count}, Consulting ratio: {consulting_ratio:.2f}, Avg duration: {avg_duration:.1f}m"

CORE_SKILLS = ["embeddings", "sentence-transformers", "vector search", "semantic search", "retrieval",
               "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "faiss",
               "ndcg", "mrr", "map", "evaluation frameworks", "python"]

NICE_TO_HAVE_SKILLS = ["lora", "qlora", "peft", "fine-tuning", "fine-tuning llms", "llm fine-tuning",
                       "xgboost", "learning to rank", "ltr", "pytorch", "transformers", "mlops"]

def get_skills_score(skills):
    if not skills:
        return 0.0, []
    matched_skills = []
    score = 0.0
    has_python = False
    for sk in skills:
        name = str(sk.get("name", "")).lower()
        prof = sk.get("proficiency", "beginner")
        dur = sk.get("duration_months", 0)
        if prof == "expert" and dur == 0:
            continue
        if name == "python":
            has_python = True
            if dur >= 12:
                score += 0.2
            else:
                score += 0.1
        is_core = any(cs in name for cs in CORE_SKILLS) or name in CORE_SKILLS
        is_nice = any(ns in name for ns in NICE_TO_HAVE_SKILLS) or name in NICE_TO_HAVE_SKILLS
        prof_multiplier = {"beginner": 0.5, "intermediate": 0.8, "advanced": 1.0, "expert": 1.2}[prof]
        dur_multiplier = min(1.2, max(0.5, dur / 24.0))
        if is_core:
            score += 0.15 * prof_multiplier * dur_multiplier
            matched_skills.append(name)
        elif is_nice:
            score += 0.08 * prof_multiplier * dur_multiplier
            matched_skills.append(name)
    if not has_python:
        score *= 0.5
    return min(1.0, score), matched_skills

def get_behavioral_score(signals):
    last_active_s = signals.get("last_active_date")
    if not last_active_s:
        return 0.1
    try:
        last_act = datetime.strptime(last_active_s, "%Y-%m-%d")
        active_days_ago = (datetime(2026, 7, 2) - last_act).days
        if active_days_ago <= 30:
            act_mult = 1.0
        elif active_days_ago <= 90:
            act_mult = 0.9
        elif active_days_ago <= 180:
            act_mult = 0.7
        elif active_days_ago <= 365:
            act_mult = 0.4
        else:
            act_mult = 0.1
    except Exception:
        act_mult = 0.5
    response_rate = signals.get("recruiter_response_rate", 0.0)
    if response_rate >= 0.8:
        resp_mult = 1.0
    elif response_rate >= 0.5:
        resp_mult = 0.9
    elif response_rate >= 0.2:
        resp_mult = 0.7
    else:
        resp_mult = 0.4
    open_to_work = signals.get("open_to_work_flag", False)
    open_mult = 1.0 if open_to_work else 0.7
    notice_days = signals.get("notice_period_days", 180)
    if notice_days <= 30:
        notice_mult = 1.0
    elif notice_days <= 60:
        notice_mult = 0.9
    elif notice_days <= 90:
        notice_mult = 0.7
    else:
        notice_mult = 0.5
    github_score = signals.get("github_activity_score", -1)
    if github_score > 50:
        gh_mult = 1.1
    elif github_score == -1:
        gh_mult = 0.9
    else:
        gh_mult = 1.0
    return act_mult * resp_mult * open_mult * notice_mult * gh_mult

scored_candidates = []
with open(candidates_file, "r", encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        cid = c["candidate_id"]
        if cid in honeypot_ids:
            continue
        profile = c.get("profile", {})
        yoe = profile.get("years_of_experience", 0)
        location = profile.get("location", "")
        country = profile.get("country", "")
        willing_relocate = c.get("redrob_signals", {}).get("willing_to_relocate", False)
        
        exp_score = get_experience_score(yoe)
        loc_score = get_location_score(location, country, willing_relocate)
        
        # If loc_score is 0.0, it means they are not located in target cities and unwilling to relocate.
        # Let's filter them out completely (or they get score 0).
        if loc_score == 0.0:
            continue
            
        career_score, career_info = get_career_score(c.get("career_history", []))
        # If career_score is 0.0, they have no ML relevance
        if career_score < 0.1:
            continue
            
        skills_score, matched_skills = get_skills_score(c.get("skills", []))
        # If skills_score is very low, skip
        if skills_score < 0.1:
            continue
            
        behavior_mult = get_behavioral_score(c.get("redrob_signals", {}))
        if behavior_mult < 0.1:
            continue
            
        base_score = (0.35 * skills_score + 0.35 * career_score + 0.15 * exp_score + 0.15 * loc_score)
        final_score = base_score * behavior_mult
        
        scored_candidates.append({
            "candidate_id": cid,
            "name": profile.get("anonymized_name"),
            "title": profile.get("current_title"),
            "company": profile.get("current_company"),
            "yoe": yoe,
            "location": f"{location}, {country}",
            "willing_to_relocate": willing_relocate,
            "skills_score": skills_score,
            "career_score": career_score,
            "exp_score": exp_score,
            "loc_score": loc_score,
            "behavior_mult": behavior_mult,
            "score": final_score,
            "matched_skills": matched_skills,
            "career_info": career_info
        })

print(f"Scored {len(scored_candidates)} valid candidates.")
scored_candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))

print("\n--- TOP 20 REFINED CANDIDATES ---")
for i, cand in enumerate(scored_candidates[:20]):
    print(f"\nRank {i+1}: {cand['candidate_id']} | Score: {cand['score']:.4f} | Name: {cand['name']}")
    print(f"  Title: {cand['title']} at {cand['company']} | YoE: {cand['yoe']} | Location: {cand['location']} | Relocate: {cand['willing_to_relocate']}")
    print(f"  Skills: {cand['matched_skills'][:8]}")
    print(f"  Career Info: {cand['career_info']}")
    print(f"  Scores - Skills: {cand['skills_score']:.3f}, Career: {cand['career_score']:.3f}, Exp: {cand['exp_score']:.3f}, Loc: {cand['loc_score']:.3f}, Behavior: {cand['behavior_mult']:.3f}")
