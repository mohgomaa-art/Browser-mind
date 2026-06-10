import json
import os
import datetime
from pathlib import Path
from typing import Any, Dict

class R0Logger:
    """
    R0Logger — Logs architectural evidence events during workflow executions.
    Also compiles resource pressure, resource acquisition, authority boundary,
    and cross environment reports from the accumulated evidence ledger.
    """

    @staticmethod
    def log_event(store_dir: str, event_type: str, **kwargs) -> None:
        """
        Log an event to the R0 Evidence Ledger (r0_evidence_ledger.jsonl).
        If the event is a resource_acquisition, also writes to the dedicated
        resource_acquisition_ledger.jsonl (P7C.5 raw truth).
        """
        ledger_path = Path(store_dir) / "r0_evidence_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "event": event_type,
            "timestamp": datetime.datetime.now().isoformat(),
            **kwargs
        }
        
        try:
            with open(ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"  [R0Logger] Failed to write to ledger: {e}")
            
        if event_type == "resource_acquisition":
            acq_ledger_path = Path(store_dir) / "resource_acquisition_ledger.jsonl"
            try:
                with open(acq_ledger_path, "a", encoding="utf-8") as f:
                    acq_entry = {k: v for k, v in entry.items() if k != "event"}
                    f.write(json.dumps(acq_entry) + "\n")
            except Exception as e:
                print(f"  [R0Logger] Failed to write to acquisition ledger: {e}")

    @staticmethod
    def generate_reports(store_dir: str) -> Dict[str, Any]:
        """
        Read the r0_evidence_ledger.jsonl and synthesize all reports:
        1. resource_pressure_report.json
        2. resource_acquisition_report.json
        3. authority_boundary_report.json
        4. cross_environment_report.json
        5. resource_class_distribution_report.json
        6. workflow_dependency_report.json
        7. provider_effectiveness_report.json  (P7C.5)
        """
        ledger_path = Path(store_dir) / "r0_evidence_ledger.jsonl"
        
        resource_pressure: Dict[str, int] = {}
        resource_acquisition: Dict[str, Any] = {}
        authority_boundary: Dict[str, int] = {}
        cross_environment = {
            "pause_resume_success_rate": 0.0,
            "resource_acquisition_events": 0,
            "pause_count": 0,
            "resume_success_rate": 0.0,
            "acquisition_duration_avg": 0.0
        }
        resource_class_distribution = {
            "Document": 0,
            "Identity": 0,
            "Secret": 0,
            "Verification": 0,
            "Authority": 0  # P7C.5: Separated from Verification
        }
        workflow_dependencies: Dict[str, Any] = {}
        # P7C.5: {resource: {provider: {attempts, successes, total_ms}}}
        provider_stats: Dict[str, Dict[str, Dict]] = {}
        
        if not ledger_path.exists():
            print(f"  [R0Logger] Warning: Ledger file {ledger_path} not found. Synthesizing empty reports.")
        else:
            events = []
            try:
                with open(ledger_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))
            except Exception as e:
                print(f"  [R0Logger] Error reading ledger: {e}")
            
            pauses = []
            resumes = []
            acquisition_durations = []
            active_pauses = {}
            
            for ev in events:
                event_type = ev.get("event")
                timestamp_str = ev.get("timestamp")
                
                # P7A: Resource class distribution aggregation
                r_class = ev.get("resource_class")
                if r_class and (event_type in ("resource_demand", "authority_challenge")):
                    if r_class in resource_class_distribution:
                        resource_class_distribution[r_class] += 1
                    else:
                        resource_class_distribution[r_class] = 1
                
                # P7B: Dependency Order extraction
                if event_type == "workflow_dependency":
                    wf = ev.get("workflow")
                    req_order = ev.get("observed_sequence")
                    if wf and req_order:
                        workflow_dependencies[wf] = req_order

                if event_type == "resource_demand":
                    res = ev.get("resource")
                    if res:
                        resource_pressure[res] = resource_pressure.get(res, 0) + 1
                        
                elif event_type == "resource_acquisition":
                    res = ev.get("resource")
                    if res:
                        if res not in resource_acquisition:
                            resource_acquisition[res] = {
                                "requested": 0, "available": 0,
                                "missing": 0, "acquired_from": {}
                            }
                        resource_acquisition[res]["requested"] += 1
                        resolved_by = ev.get("resolved_by")
                        attempts = ev.get("attempts", [])
                        duration_ms = ev.get("duration_ms", 0)
                        
                        if resolved_by:
                            resource_acquisition[res]["available"] += 1
                            resource_acquisition[res]["acquired_from"][resolved_by] = \
                                resource_acquisition[res]["acquired_from"].get(resolved_by, 0) + 1
                        else:
                            resource_acquisition[res]["missing"] += 1

                        # P7C.5: Track every attempted provider for this resource
                        if res not in provider_stats:
                            provider_stats[res] = {}
                        for attempted in attempts:
                            if attempted not in provider_stats[res]:
                                provider_stats[res][attempted] = {"attempts": 0, "successes": 0, "total_ms": 0}
                            provider_stats[res][attempted]["attempts"] += 1
                            if attempted == resolved_by:
                                provider_stats[res][attempted]["successes"] += 1
                                provider_stats[res][attempted]["total_ms"] += duration_ms

                elif event_type == "authority_challenge":
                    challenge = ev.get("challenge_type")
                    if challenge:
                        authority_boundary[challenge] = authority_boundary.get(challenge, 0) + 1
                        
                elif event_type == "workflow_pause":
                    pauses.append(ev)
                    cross_environment["pause_count"] += 1
                    if ev.get("acquisition_required", False):
                        cross_environment["resource_acquisition_events"] += 1
                    wf = ev.get("workflow")
                    env = ev.get("environment")
                    step = ev.get("step_index")
                    res = ev.get("resource")
                    if timestamp_str and wf and env and step:
                        active_pauses[(wf, env, step, res)] = timestamp_str
                        
                elif event_type == "workflow_resume":
                    resumes.append(ev)
                    wf = ev.get("workflow")
                    env = ev.get("environment")
                    step = ev.get("step_index")
                    match_key = None
                    for key in list(active_pauses.keys()):
                        if key[0] == wf and key[1] == env and key[2] == step:
                            match_key = key
                            break
                    if match_key and timestamp_str:
                        pause_time_str = active_pauses.pop(match_key)
                        try:
                            t_pause = datetime.datetime.fromisoformat(pause_time_str)
                            t_resume = datetime.datetime.fromisoformat(timestamp_str)
                            dur = (t_resume - t_pause).total_seconds()
                            acquisition_durations.append(dur)
                        except Exception as e:
                            print(f"  [R0Logger] Error parsing timestamps for duration: {e}")
            
            if len(pauses) > 0:
                success_resumes = sum(1 for r in resumes if r.get("status") == "SUCCESS")
                cross_environment["pause_resume_success_rate"] = round(len(resumes) / len(pauses), 2)
                cross_environment["resume_success_rate"] = round(success_resumes / max(len(resumes), 1), 2)
            else:
                cross_environment["pause_resume_success_rate"] = 1.0
                cross_environment["resume_success_rate"] = 1.0
                
            if len(acquisition_durations) > 0:
                cross_environment["acquisition_duration_avg"] = round(
                    sum(acquisition_durations) / len(acquisition_durations), 2
                )

        # P7C.5: Synthesize provider_effectiveness_report
        provider_effectiveness: Dict[str, Any] = {}
        for res, providers in provider_stats.items():
            provider_effectiveness[res] = {}
            for provider, stats in providers.items():
                a = stats["attempts"]
                s = stats["successes"]
                ms = stats["total_ms"]
                provider_effectiveness[res][provider] = {
                    "success_rate": round(s / a, 2) if a else 0.0,
                    "avg_latency_ms": round(ms / s, 1) if s else None
                }

        # P7D: Detect provider gaps (resources with 0% success across ALL providers)
        try:
            from browsermind_core.runtime.provider_selector import ProviderGapDetector
            provider_gap = ProviderGapDetector.detect_gaps(provider_effectiveness)
        except Exception:
            provider_gap = {}

        try:
            reports_to_save = {
                "resource_pressure_report.json": resource_pressure,
                "resource_acquisition_report.json": resource_acquisition,
                "authority_boundary_report.json": authority_boundary,
                "cross_environment_report.json": cross_environment,
                "resource_class_distribution_report.json": resource_class_distribution,
                "workflow_dependency_report.json": workflow_dependencies,
                "provider_effectiveness_report.json": provider_effectiveness,
                "provider_gap_report.json": provider_gap
            }
            for filename, data in reports_to_save.items():
                file_path = Path(store_dir) / filename
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"  [R0Logger] Generated: {file_path}")
        except Exception as e:
            print(f"  [R0Logger] Failed to write reports: {e}")
            
        return {
            "resource_pressure": resource_pressure,
            "resource_acquisition": resource_acquisition,
            "authority_boundary": authority_boundary,
            "cross_environment": cross_environment,
            "resource_class_distribution": resource_class_distribution,
            "workflow_dependencies": workflow_dependencies,
            "provider_effectiveness": provider_effectiveness
        }
