import json
import os
from datetime import datetime

base_dir = r"d:\OneDrive\Desktop\hack2skill\data\[PUB] India_runs_data_and_ai_challenge\India_runs_data_and_ai_challenge"
candidates_file = os.path.join(base_dir, "candidates.jsonl")

print("Scanning candidates for strict physical contradictions...")

impossible_last_active = []
impossible_edu_dates = []
impossible_job_dates = []
impossible_skills = []
impossible_yoe_vs_job_dur = []
impossible_yoe_vs_edu_start = []
impossible_job_overlaps = []

count = 0
with open(candidates_file, "r", encoding="utf-8") as f:
    for line in f:
        count += 1
        c = json.loads(line)
        cid = c["candidate_id"]
        profile = c.get("profile", {})
        skills = c.get("skills", [])
        history = c.get("career_history", [])
        edu = c.get("education", [])
        signals = c.get("redrob_signals", {})
        
        # 1. last_active_date < signup_date
        signup_s = signals.get("signup_date")
        last_act_s = signals.get("last_active_date")
        if signup_s and last_act_s:
            try:
                signup = datetime.strptime(signup_s, "%Y-%m-%d")
                last_act = datetime.strptime(last_act_s, "%Y-%m-%d")
                if last_act < signup:
                    impossible_last_active.append(cid)
            except Exception:
                pass
                
        # 2. edu: end_year < start_year
        for ed in edu:
            syr = ed.get("start_year")
            eyr = ed.get("end_year")
            if syr and eyr and eyr < syr:
                impossible_edu_dates.append(cid)
                break
                
        # 3. job: end_date < start_date
        for job in history:
            start_s = job.get("start_date")
            end_s = job.get("end_date")
            if start_s and end_s:
                try:
                    s = datetime.strptime(start_s, "%Y-%m-%d")
                    e = datetime.strptime(end_s, "%Y-%m-%d")
                    if e < s:
                        impossible_job_dates.append(cid)
                        break
                except Exception:
                    pass
                    
        # 4. Expert proficiency with 0 duration_months
        # "expert proficiency in 10 skills with 0 years used"
        expert_zero_dur = 0
        for sk in skills:
            if sk.get("proficiency") == "expert" and sk.get("duration_months", 0) == 0:
                expert_zero_dur += 1
        if expert_zero_dur >= 5: # e.g. multiple expert skills with 0 duration
            impossible_skills.append(cid)
            
        # 5. yoe vs job duration
        yoe = profile.get("years_of_experience", 0)
        total_job_months = sum([job.get("duration_months", 0) for job in history])
        total_job_years = total_job_months / 12.0
        # If total job duration is 8 years, but years_of_experience is at a company founded 3 years ago?
        # Wait, let's see: "8 years of experience at a company founded 3 years ago"
        # How would we check "company founded 3 years ago"?
        # Wait! Is there a company table or founding year database? No.
        # But wait! If a candidate has a single job at a company, and the duration_months is 96 (8 years),
        # but the company size is "1-10" and the company name is something specific, or maybe the company start_date and end_date has some contradiction?
        # Or maybe "8 years of experience at a company founded 3 years ago" means the candidate claims 8 years of experience, but their only job has a duration of 3 years? Or vice versa?
        # Let's check.
        
        # 6. yoe vs edu
        # Work starts way before education ends or starts
        first_work_year = 9999
        for job in history:
            start_s = job.get("start_date")
            if start_s:
                try:
                    yr = int(start_s.split("-")[0])
                    if yr < first_work_year:
                        first_work_year = yr
                except Exception:
                    pass
        earliest_edu_year = 9999
        for ed in edu:
            syr = ed.get("start_year")
            if syr and syr < earliest_edu_year:
                earliest_edu_year = syr
        if earliest_edu_year != 9999 and yoe > (2026 - earliest_edu_year) + 2:
            impossible_yoe_vs_edu_start.append(cid)

print(f"Total candidates scanned: {count}")
print(f"Impossible last active date: {len(impossible_last_active)}")
print(f"Impossible edu dates: {len(impossible_edu_dates)}")
print(f"Impossible job dates: {len(impossible_job_dates)}")
print(f"Impossible expert skills: {len(impossible_skills)}")
print(f"Impossible YOE vs Edu: {len(impossible_yoe_vs_edu_start)}")

# Let's see intersection of these
all_anomalous = set(impossible_last_active) | set(impossible_edu_dates) | set(impossible_job_dates) | set(impossible_skills) | set(impossible_yoe_vs_edu_start)
print(f"Total unique anomalous candidates: {len(all_anomalous)}")

# Let's print some of them
print("Sample anomalous IDs:")
print(list(all_anomalous)[:20])
