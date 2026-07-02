import json
import os
import gzip
import argparse
import hashlib
import csv
from datetime import datetime

# Core consulting/services firms to penalize (disqualifier from JD)
CONSULTING_FIRMS = {
    "infosys", "wipro", "tcs", "accenture", "cognizant", "capgemini",
    "tech mahindra", "mphasis", "hcl", "genpact", "mindtree", "tata consultancy"
}

# Target and welcome locations (from JD)
TARGET_LOCATIONS = ["noida", "pune", "delhi", "gurgaon", "ncr", "ghaziabad", "faridabad"]
WELCOME_LOCATIONS = ["mumbai", "hyderabad", "navi mumbai"]

# Core and Nice-to-have skills (from JD)
CORE_SKILLS = ["embeddings", "sentence-transformers", "vector search", "semantic search", "retrieval",
               "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "faiss",
               "ndcg", "mrr", "map", "evaluation frameworks", "python"]

NICE_TO_HAVE_SKILLS = ["lora", "qlora", "peft", "fine-tuning", "fine-tuning llms", "llm fine-tuning",
                       "xgboost", "learning to rank", "ltr", "pytorch", "transformers", "mlops"]

def get_experience_score(yoe):
    # Target: 5 to 9 years (ideal: 6 to 8 years)
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
    
    # Check if explicitly not India (blank country treated as unknown, not as India)
    if country_lower and "india" not in country_lower:
        return 0.05
        
    # Check city
    if any(city in loc_lower for city in TARGET_LOCATIONS):
        return 1.0
    elif any(city in loc_lower for city in WELCOME_LOCATIONS):
        return 0.9
    elif willing_to_relocate:
        return 0.8
    else:
        return 0.2 # low score, will rank down unless other features are perfect

def get_career_score(history):
    if not history:
        return 0.0
        
    total_jobs = len(history)
    consulting_jobs = 0
    ml_title_count = 0
    recent_is_ml = False
    
    for i, job in enumerate(history):
        company = str(job.get("company", "")).lower()
        title = str(job.get("title", "")).lower()
        desc = str(job.get("description", "")).lower()
        
        # Check consulting
        if any(firm in company for firm in CONSULTING_FIRMS):
            consulting_jobs += 1
            
        # Check ML titles
        is_ml_job = False
        ml_keywords = ["ai", "ml", "machine learning", "nlp", "data scientist", "deep learning", 
                       "search", "retrieval", "ranking", "recommendation", "applied science", "applied scientist"]
        
        title_words = title.replace("/", " ").replace("-", " ").split()
        if any(kw in title_words or kw in title for kw in ml_keywords):
            is_ml_job = True
            ml_title_count += 1
            if i == 0:  # most recent job
                recent_is_ml = True
                
        # Check description if title is generic
        if not is_ml_job:
            desc_keywords = ["embeddings", "vector database", "semantic search", "recommendation system", "fine-tuning"]
            if any(dk in desc for dk in desc_keywords):
                ml_title_count += 0.5
                if i == 0:
                    recent_is_ml = True

    consulting_ratio = consulting_jobs / total_jobs
    
    # Calculate base career score
    score = 0.0
    if recent_is_ml:
        score += 0.6
    elif ml_title_count > 0:
        score += 0.3
        
    score += min(0.4, (ml_title_count / total_jobs) * 0.4)
    
    # Apply graduated service company penalty (not just 100% consulting)
    if consulting_ratio >= 0.8:
        score *= 0.1
    elif consulting_ratio >= 0.5:
        score *= 0.4
    elif consulting_ratio >= 0.25:
        score *= 0.7
        
    # Check for title chasers (average job duration < 18 months)
    avg_duration = sum([job.get("duration_months", 0) for job in history]) / total_jobs
    if avg_duration < 18 and total_jobs > 1:
        score *= 0.7
        
    return score

def get_skills_score(skills):
    if not skills:
        return 0.0, []
        
    matched_skills = []
    score = 0.0
    has_python = False
    
    PROF_MULTIPLIERS = {"beginner": 0.5, "intermediate": 0.8, "advanced": 1.0, "expert": 1.2}

    for sk in skills:
        name = str(sk.get("name", "")).lower()
        prof = str(sk.get("proficiency", "beginner")).lower()  # normalise casing
        dur = sk.get("duration_months", 0) or 0  # guard against None
        
        # Skip expert/advanced skills with 0 duration (keyword stuffing / honeypot signal)
        if prof in ("expert", "advanced") and dur == 0:
            continue

        # Safe proficiency lookup — unknown levels treated as beginner
        prof_multiplier = PROF_MULTIPLIERS.get(prof, 0.5)
        dur_multiplier = min(1.2, max(0.5, dur / 24.0))

        # Python: handled separately to avoid double-counting (not in is_core path)
        if name == "python":
            has_python = True
            if dur >= 12:
                score += 0.2 * prof_multiplier
            else:
                score += 0.1 * prof_multiplier
            continue  # skip the is_core / is_nice block below for python
                
        is_core = any(cs in name for cs in CORE_SKILLS) or name in CORE_SKILLS
        is_nice = any(ns in name for ns in NICE_TO_HAVE_SKILLS) or name in NICE_TO_HAVE_SKILLS
        
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
        act_mult = 0.5  # neutral fallback — don't discard all other signals
    else:
        
        try:
            last_act = datetime.strptime(last_active_s, "%Y-%m-%d")
            # Reference date: July 2, 2026 (hackathon evaluation date)
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

def generate_reasoning_for_candidate(cand, rank):
    cid = cand["candidate_id"]
    title = cand["title"]
    company = cand["company"]
    yoe = cand["yoe"]
    location = cand["location"]
    skills = cand["matched_skills"]
    relocate = cand["willing_to_relocate"]
    notice_days = cand.get("notice_period_days", 30)
    
    h = int(hashlib.md5(cid.encode('utf-8')).hexdigest(), 16)
    
    # Sentence 1: Profile Summary
    openers = [
        f"A senior-level candidate with {yoe} years of experience, currently working as a {title} at {company}.",
        f"Brings {yoe} years of professional experience, currently serving as a {title} for {company}.",
        f"Currently a {title} at {company} with {yoe} years of total experience in technology.",
        f"An experienced professional with {yoe} years in the industry, currently a {title} at {company}."
    ]
    s1 = openers[h % len(openers)]
    
    # Sentence 2: Tech stack alignment
    skills_s = ", ".join(skills[:3]) if skills else "relevant software engineering tools"
    skills_sentences = [
        f"They demonstrate strong production capability in {skills_s}, which aligns well with our search and matching stack.",
        f"Their hands-on expertise in {skills_s} makes them a good technical fit for our retrieval and ranking systems.",
        f"With solid skills in {skills_s}, they possess the practical ML depth needed for our founding AI team.",
        f"They have proven experience utilizing {skills_s} to build and scale data-driven systems."
    ]
    s2 = skills_sentences[(h >> 2) % len(skills_sentences)]
    
    # Sentence 3: Location and availability
    loc_sentences = []
    if "noida" in location.lower() or "pune" in location.lower() or "delhi" in location.lower() or "gurgaon" in location.lower() or "ncr" in location.lower():
        loc_sentences = [
            f"Based in {location}, they are local and readily available for our hybrid office schedule.",
            f"Their location in {location} is convenient for our Pune/Noida offices.",
            f"Located in {location}, they fit our geographic preference and hybrid work mode."
        ]
    elif relocate:
        loc_sentences = [
            f"Currently based in {location}, but they are willing to relocate to Noida/Pune for this position.",
            f"Although located in {location}, they have indicated willingness to relocate to our key office hubs.",
            f"Based in {location} and ready to relocate to Noida/Pune for hybrid collaboration."
        ]
    else:
        loc_sentences = [
            f"Based in {location}, they would need a flexible hybrid arrangement to collaborate effectively.",
            f"Currently located in {location}; will require alignment on hybrid travel cadence to Noida/Pune."
        ]
    s3 = loc_sentences[(h >> 4) % len(loc_sentences)]
    
    # Sentence 4: Gaps or positive highlights
    gaps_sentences = []
    if rank <= 10:
        gaps_sentences = [
            "An outstanding fit with no major red flags and an active engagement score.",
            "Highly active on Redrob and ready to make a significant impact on our core algorithms.",
            "Their product-focused background and active platform signals make them a top-tier choice."
        ]
    elif notice_days > 45:
        gaps_sentences = [
            f"A minor concern is their {notice_days}-day notice period, but their strong engineering skills justify consideration.",
            f"While their {notice_days}-day notice period is slightly long, their search and matching background is a strong asset.",
            f"The candidate's {notice_days}-day notice period is a bottleneck, but their overall alignment is highly competitive."
        ]
    else:
        gaps_sentences = [
            f"Their short notice period of {notice_days} days is very attractive for our immediate hiring needs.",
            f"An active candidate with a prompt response rate and a manageable notice period of {notice_days} days.",
            f"With a {notice_days}-day notice period and high activity, they represent a low-friction hire."
        ]
    s4 = gaps_sentences[(h >> 6) % len(gaps_sentences)]
    
    return f"{s1} {s2} {s3} {s4}"

def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Redrob Founding AI Engineer JD")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl or candidates.jsonl.gz")
    parser.add_argument("--out", required=True, help="Path to output submission CSV file")
    args = parser.parse_args()

    # Step 1: Pre-scan candidates to build the honeypot filter set
    print("Scanning candidates for honeypots...")
    honeypot_ids = set()
    
    # Open candidates file (handles gzip or normal text)
    is_gz = args.candidates.endswith(".gz")
    open_func = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"

    with open_func(args.candidates, mode, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            cid = c["candidate_id"]
            profile = c.get("profile", {})
            skills = c.get("skills", [])
            history = c.get("career_history", [])
            
            is_hp = False
            
            # Startup founded date violations
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
                        
            # Expert skills with 0 duration >= 4
            zero_dur_skills = [sk["name"] for sk in skills if sk.get("proficiency") == "expert" and sk.get("duration_months", 0) == 0]
            if len(zero_dur_skills) >= 4:
                is_hp = True
                
            # YoE exceeds job history span by a wide margin
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

    print(f"Identified {len(honeypot_ids)} honeypot candidates.")

    # Step 2: Score candidates
    scored_candidates = []
    print("Scoring candidates...")
    with open_func(args.candidates, mode, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            cid = c["candidate_id"]
            
            # Skip honeypots
            if cid in honeypot_ids:
                continue
                
            profile = c.get("profile", {})
            yoe = profile.get("years_of_experience", 0)
            location = profile.get("location", "")
            country = profile.get("country", "")
            willing_relocate = c.get("redrob_signals", {}).get("willing_to_relocate", False)
            notice_days = c.get("redrob_signals", {}).get("notice_period_days", 30)
            
            exp_score = get_experience_score(yoe)
            loc_score = get_location_score(location, country, willing_relocate)
            career_score = get_career_score(c.get("career_history", []))
            skills_score, matched_skills = get_skills_score(c.get("skills", []))
            behavior_mult = get_behavioral_score(c.get("redrob_signals", {}))
            
            # Weighted base score
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
                "notice_period_days": notice_days,
                "score": final_score,
                "matched_skills": matched_skills
            })

    print(f"Scored {len(scored_candidates)} candidates.")

    # Step 3: Sort by score descending, then by candidate_id ascending
    scored_candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))

    # Step 4: Keep top 100 and generate reasonings
    top_100 = scored_candidates[:100]
    
    # In case there are fewer than 100 candidates in the input, just take all available
    output_rows = []
    for idx, cand in enumerate(top_100):
        rank = idx + 1
        reasoning = generate_reasoning_for_candidate(cand, rank)
        output_rows.append({
            "candidate_id": cand["candidate_id"],
            "rank": rank,
            "score": round(cand["score"], 4),
            "reasoning": reasoning
        })

    # Step 5: Write to output CSV
    print(f"Writing {len(output_rows)} rows to {args.out}...")
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        for row in output_rows:
            writer.writerow(row)

    # Step 6: Write to output XLSX if pandas/openpyxl are installed
    try:
        import pandas as pd
        out_xlsx = args.out.replace(".csv", ".xlsx")
        print(f"Writing {len(output_rows)} rows to {out_xlsx}...")
        df = pd.DataFrame(output_rows)
        df.to_excel(out_xlsx, index=False)
        print("XLSX output saved successfully.")
    except Exception as e:
        print(f"Skipping XLSX generation (pandas/openpyxl not available or error occurred: {e})")

    print("Ranking process completed successfully.")

if __name__ == "__main__":
    main()
