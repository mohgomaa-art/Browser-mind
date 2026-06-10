"""
BrowserMind -- Scar Analytics Report Generator
==============================================
Aggregates scar telemetry from logs/observatory/scar_index.jsonl
and failure details to output global statistics.

Usage:
  python scripts/scar_report.py
"""

import json
from pathlib import Path

def generate_report():
    index_file = Path("logs/observatory/scar_index.jsonl")
    failures_dir = Path("logs/observatory/failures")

    # Initialize stats
    report = {
        "total_scars": 0,
        "unknown_company": 0,
        "unknown_workflow": 0,
        "unknown_environment": 0,
        "by_environment": {},
        "by_company": {},
        "by_instance": {},
        "by_workflow_family": {},
        "by_phase": {},
        "by_severity": {},
        "by_evidence_quality": {},
        "by_provider": {},
        "by_resource": {},
        "by_mission_family": {},
        "unclassified": 0
    }

    try:
        lines = []
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                report["total_scars"] += 1
                
                # Environment Family
                env = record.get("environment_family", "unknown")
                report["by_environment"][env] = report["by_environment"].get(env, 0) + 1
                if env == "unknown":
                    report["unknown_environment"] += 1

                # Company Name
                company = record.get("company_name", "unknown")
                report["by_company"][company] = report["by_company"].get(company, 0) + 1
                if company == "unknown":
                    report["unknown_company"] += 1

                # Environment Instance
                instance = record.get("environment_instance", "unknown")
                report["by_instance"][instance] = report["by_instance"].get(instance, 0) + 1

                # Workflow Family
                wf_fam = record.get("workflow_family", "unknown")
                report["by_workflow_family"][wf_fam] = report["by_workflow_family"].get(wf_fam, 0) + 1
                if wf_fam == "unknown":
                    report["unknown_workflow"] += 1

                # Phase
                phase = record.get("phase", "unknown")
                report["by_phase"][phase] = report["by_phase"].get(phase, 0) + 1

                # Severity
                severity = record.get("severity", "unknown")
                report["by_severity"][severity] = report["by_severity"].get(severity, 0) + 1

                # Evidence Quality
                eq = record.get("evidence_quality", "unknown")
                report["by_evidence_quality"][eq] = report["by_evidence_quality"].get(eq, 0) + 1

                # Mission Family
                m_fam = record.get("mission_family", "none")
                report["by_mission_family"][m_fam] = report["by_mission_family"].get(m_fam, 0) + 1


                # Unclassified status
                if record.get("status") == "unclassified":
                    report["unclassified"] += 1

                # Extract providers and resources from individual failure records
                exec_id = record.get("execution_id")
                if exec_id:
                    failure_file = failures_dir / f"failure_{exec_id}.json"
                    if failure_file.exists():
                        try:
                            with open(failure_file, "r", encoding="utf-8") as ff:
                                fail_data = json.load(ff)
                                ctx = fail_data.get("execution_context", {})
                                
                                # Provider Chain
                                for prov in ctx.get("provider_chain", []):
                                    report["by_provider"][prov] = report["by_provider"].get(prov, 0) + 1
                                    
                                # Resource Dependencies
                                for res in ctx.get("resource_dependencies", []):
                                    report["by_resource"][res] = report["by_resource"].get(res, 0) + 1
                        except Exception:
                            pass
    except Exception as e:
        print(f"Error generating report: {e}")
        return

    # Aggregate Mission Run Metrics from harvest_records
    mission_stats = {}
    harvest_dir = Path("logs/observatory/harvest_records")
    if harvest_dir.exists():
        for f_path in harvest_dir.glob("*.json"):
            try:
                with open(f_path, "r", encoding="utf-8") as hf:
                    data = json.load(hf)
                    ctx = data.get("execution_context", {})
                    m_id = ctx.get("mission_id")
                    m_family = ctx.get("mission_family") or data.get("environment_family") or "unknown"
                    success = data.get("success", False)
                    
                    if m_id:
                        if m_id not in mission_stats:
                            mission_stats[m_id] = {
                                "mission_id": m_id,
                                "family": m_family,
                                "total_runs": 0,
                                "successes": 0,
                                "failures": 0
                            }
                        
                        mission_stats[m_id]["total_runs"] += 1
                        if success:
                            mission_stats[m_id]["successes"] += 1
                        else:
                            mission_stats[m_id]["failures"] += 1
            except Exception:
                pass

    # Format the mission metrics
    formatted_mission_metrics = {}
    for m_id, stats in mission_stats.items():
        total = stats["total_runs"]
        succs = stats["successes"]
        fails = stats["failures"]
        
        success_rate = round((succs / total) * 100, 1) if total > 0 else 0.0
        variance = round((min(succs, fails) / total) * 100, 1) if total > 0 else 0.0
        
        formatted_mission_metrics[m_id] = {
            "family": stats["family"],
            "total_runs": total,
            "successes": succs,
            "failures": fails,
            "success_rate_pct": success_rate,
            "variance_pct": variance
        }
        
    report["mission_run_metrics"] = formatted_mission_metrics

    # Print pretty JSON representation
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    generate_report()
