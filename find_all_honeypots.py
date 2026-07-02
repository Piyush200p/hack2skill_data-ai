import json
import os
from datetime import datetime

base_dir = r"d:\OneDrive\Desktop\hack2skill\data\[PUB] India_runs_data_and_ai_challenge\India_runs_data_and_ai_challenge"
candidates_file = os.path.join(base_dir, "candidates.jsonl")

print("Scanning for all possible honeypot matches...")

honeypots = []

with open(candidates_file, "r", encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        cid = c["candidate_id"]
        profile = c.get("profile", {})
        skills = c.get("skills", [])
        history = c.get("career_history", [])
        
        is_honeypot = False
        reasons = []
        
        # 1. Startup anomalies (Krutrim and Sarvam AI founded in 2023, Rephrase.ai in 2019)
        for job in history:
            company = job.get("company", "")
            start_date_s = job.get("start_date")
            if start_date_s:
                try:
                    start_year = int(start_date_s.split("-")[0])
                    if "krutrim" in company.lower() and start_year < 2023:
                        is_honeypot = True
                        reasons.append(f"Worked at Krutrim in {start_year} (founded late 2023)")
                    elif "sarvam" in company.lower() and start_year < 2023:
                        is_honeypot = True
                        reasons.append(f"Worked at Sarvam AI in {start_year} (founded mid 2023)")
                    elif "rephrase" in company.lower() and start_year < 2019:
                        is_honeypot = True
                        reasons.append(f"Worked at Rephrase.ai in {start_year} (founded 2019)")
                except Exception:
                    pass
        
        # 2. Skill duration anomaly: 10 skills with 0 duration_months (any proficiency, or expert/advanced)
        # "expert proficiency in 10 skills with 0 years used"
        zero_dur_skills = [sk["name"] for sk in skills if sk.get("proficiency") == "expert" and sk.get("duration_months", 0) == 0]
        if len(zero_dur_skills) >= 4: # let's check if there are any with >= 4
            is_honeypot = True
            reasons.append(f"Expert skills with 0 duration: {zero_dur_skills}")
            
        # 3. Double check other impossible dates
        # check if years_of_experience is much larger than career history span
        # e.g., years_of_experience is 15 but earliest job start is 2024
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
                is_honeypot = True
                reasons.append(f"YoE {yoe} exceeds job history span starting in {earliest_job_year}")
                
        if is_honeypot:
            honeypots.append({
                "candidate_id": cid,
                "reasons": reasons
            })

print(f"Total honeypots found: {len(honeypots)}")
for h in honeypots[:20]:
    print(h)
