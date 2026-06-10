import sys
import os
import re

def clean_url(url_str):
    url_str = url_str.replace("`", "").strip()
    match = re.search(r'(https?://[^\s\)]+)', url_str)
    if match:
        return match.group(1).strip()
    return url_str

def clean_text(val_str):
    return val_str.strip().replace('"', '\\"')

def main():
    if len(sys.argv) < 2:
        print("Usage: python get_mission.py <MISSION_ID>")
        return

    mission_id = sys.argv[1].strip().upper()
    
    missions_file = os.path.join("DOCS", "production_missions_r2a.md")
    if not os.path.exists(missions_file):
        print(f"Missions file not found at {missions_file}")
        return

    with open(missions_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_family = "unknown"
    target_lines = []
    capture = False

    for line in lines:
        line_str = line.strip()
        
        # Track families/parts headers
        if line_str.startswith("### Family") or line_str.startswith("## Part"):
            header_lower = line_str.lower()
            if "upload" in header_lower:
                current_family = "upload_autofill_stress"
            elif "stability" in header_lower:
                current_family = "replay_stability"
            elif "state decay" in header_lower:
                current_family = "state_decay"
            elif "resource timing" in header_lower:
                current_family = "resource_timing"
            elif "transfer" in header_lower:
                current_family = "transfer_robustness"
            elif "authentication" in header_lower:
                current_family = "auth_recovery"
            elif "verification" in header_lower:
                current_family = "verification_identity"

        # Check for mission start
        if re.match(r'^#+\s+Mission\s+', line_str):
            # If we were capturing a previous mission, stop
            if capture:
                break
            # Check if this is our target mission
            if mission_id in line_str.upper():
                capture = True
                target_lines.append(line)
            continue
            
        if capture:
            # If we hit the next header, stop capturing
            if line_str.startswith("---") or re.match(r'^#+\s+', line_str):
                break
            target_lines.append(line)

    if not target_lines:
        print(f"Mission {mission_id} not found in registry.")
        return

    title = ""
    target_sites = []
    goal = ""
    repetitions = 1
    hypothesis = ""

    for line in target_lines:
        line_str = line.strip()
        if line_str.startswith("- **Title**"):
            title = line_str.split(":", 1)[1].strip()
        elif line_str.startswith("- **Target Site**") or line_str.startswith("- **Target Site 1**"):
            target_sites.append(clean_url(line_str.split(":", 1)[1].strip()))
        elif line_str.startswith("- **Target Site 2**"):
            target_sites.append(clean_url(line_str.split(":", 1)[1].strip()))
        elif line_str.startswith("- **Target Site 3**"):
            target_sites.append(clean_url(line_str.split(":", 1)[1].strip()))
        elif line_str.startswith("- **Target Site 4**"):
            target_sites.append(clean_url(line_str.split(":", 1)[1].strip()))
        elif line_str.startswith("- **Target Site 5**"):
            target_sites.append(clean_url(line_str.split(":", 1)[1].strip()))
        elif line_str.startswith("- **Mission Goal**"):
            goal = line_str.split(":", 1)[1].strip()
        elif line_str.startswith("- **Repetitions**"):
            try:
                repetitions = int(line_str.split(":", 1)[1].strip())
            except Exception:
                repetitions = 1
        elif line_str.startswith("- **Hypothesis Tested**"):
            hypothesis = line_str.split(":", 1)[1].strip()

    clean_title = re.sub(r'[^a-zA-Z0-9_]', '_', title.lower()).replace('__', '_').strip('_')
    safe_name = f"{mission_id}_{clean_title}"

    temp_bat = os.path.join("scratch", "temp_mission.bat")
    os.makedirs("scratch", exist_ok=True)
    with open(temp_bat, "w", encoding="utf-8") as f_out:
        f_out.write(f'@echo off\n')
        if len(target_sites) > 1:
            for idx, site in enumerate(target_sites, 1):
                f_out.write(f'set REC_URL_{idx}={site}\n')
            f_out.write(f'set REC_URL={target_sites[0]}\n')
            f_out.write(f'set REC_IS_TRANSFER=1\n')
        else:
            site = target_sites[0] if target_sites else ""
            f_out.write(f'set REC_URL={site}\n')
            f_out.write(f'set REC_IS_TRANSFER=0\n')
            
        f_out.write(f'set REC_GOAL={clean_text(goal)}\n')
        f_out.write(f'set REC_NAME={safe_name}\n')
        f_out.write(f'set REC_MISSION_ID={mission_id}\n')
        f_out.write(f'set REC_MISSION_FAMILY={current_family}\n')
        f_out.write(f'set REC_REPETITIONS={repetitions}\n')
        f_out.write(f'set REC_HYPOTHESIS={clean_text(hypothesis)}\n')

    print(f"Loaded Mission {mission_id}:")
    print(f"  Title:      {title}")
    print(f"  Family:     {current_family}")
    if len(target_sites) > 1:
        for idx, site in enumerate(target_sites, 1):
            print(f"  URL {idx}:      {site}")
    else:
        site = target_sites[0] if target_sites else ""
        print(f"  URL:        {site}")
    print(f"  Goal:       {goal}")
    print(f"  Reps:       {repetitions}")
    print(f"  Hypothesis: {hypothesis}")

if __name__ == "__main__":
    main()
