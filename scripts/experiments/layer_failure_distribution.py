import json
import glob
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

def generate_distribution():
    base_dir = ROOT_DIR / "reports" / "reality_test"
    
    # Find most recent test run directory
    subdirs = sorted([d for d in base_dir.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True)
    if not subdirs:
        print("No reality test reports found.")
        return
        
    latest_dir = subdirs[0]
    print(f"Analyzing reality test: {latest_dir.name}")
    
    files = glob.glob(str(latest_dir / "*" / "*.json"))
    
    counts = {
        "resolution": 0,
        "execution": 0,
        "effect": 0,
        "state": 0,
        "success": 0
    }
    
    total_replays = 0
    
    for f_path in files:
        if "summary.json" in f_path:
            continue
            
        with open(f_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
            
        total_replays += 1
        
        # Determine failure layer for the workflow
        workflow_layer = None
        
        # Check step attributions first
        attributions = report.get("failure_attribution", [])
        for attr in attributions:
            layer = attr.get("failure_layer")
            if layer:
                workflow_layer = layer
                break
                
        # If steps didn't fail, check global state
        if not workflow_layer:
            verif = report.get("verification_report")
            if verif:
                if not verif.get("state_match", False):
                    workflow_layer = "state"
            else:
                workflow_layer = "state" # If missing verif report, it failed state
                
        if workflow_layer:
            counts[workflow_layer] += 1
        else:
            counts["success"] += 1
            
    if total_replays == 0:
        print("No replays found in the report.")
        return
        
    distribution = {
        "total_replays": total_replays,
        "failures": {
            "Resolution Failures": f"{counts['resolution'] / total_replays * 100:.1f}%",
            "Execution Failures": f"{counts['execution'] / total_replays * 100:.1f}%",
            "Effect Failures": f"{counts['effect'] / total_replays * 100:.1f}%",
            "State Failures": f"{counts['state'] / total_replays * 100:.1f}%"
        },
        "success_rate": f"{counts['success'] / total_replays * 100:.1f}%",
        "raw_counts": counts
    }
    
    out_file = latest_dir / "layer_failure_distribution.json"
    out_file.write_text(json.dumps(distribution, indent=2), encoding="utf-8")
    
    print(json.dumps(distribution, indent=2))
    print(f"\nSaved distribution to {out_file}")

if __name__ == "__main__":
    generate_distribution()
