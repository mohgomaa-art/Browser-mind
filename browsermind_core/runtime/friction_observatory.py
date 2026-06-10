import json
import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any

class FrictionType(Enum):
    """
    R1: Runtime Friction Taxonomy.
    Categorizes the reasons why a workflow execution blocks, diverges, or fails.
    """
    POPUP = "Popup"             # Cookie banners, newsletters, modals
    REDIRECT = "Redirect"       # Unexpected navigation, login walls
    TIMEOUT = "Timeout"         # Infinite spinners, rate limits, slow loads
    NAVIGATION = "Navigation"   # Multi-tab issues, lost context
    UPLOAD = "Upload"           # File rejection, format errors
    AUTH = "Auth"               # Session expired, forced logout
    AUTHORITY = "Authority"     # Captcha, Terms Acceptance, Age Gate
    UNKNOWN = "Unknown"         # Unhandled exceptions

class FrictionObservatory:
    """
    P7E.5 / R1: Runtime Friction Observatory.
    Records events where execution encounters friction and generates reports
    to guide what handlers should be built next.
    """
    
    @staticmethod
    def log_friction(store_dir: str, friction_type: FrictionType, blocker_name: str, environment: str, workflow: str) -> None:
        """
        Record a friction event to the friction_ledger.jsonl
        """
        ledger_path = Path(store_dir) / "friction_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "event": "execution_blocked",
            "timestamp": datetime.datetime.now().isoformat(),
            "friction_type": friction_type.value,
            "blocker": blocker_name,
            "environment": environment,
            "workflow": workflow
        }
        
        try:
            with open(ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"  [FrictionObservatory] Failed to write to friction ledger: {e}")

    @staticmethod
    def generate_report(store_dir: str) -> Dict[str, Any]:
        """
        Reads the friction_ledger.jsonl and synthesizes the top_runtime_frictions_report.json
        """
        ledger_path = Path(store_dir) / "friction_ledger.jsonl"
        
        report = {
            "total_friction_events": 0,
            "friction_by_type": {},
            "top_blockers": {},
            "environments_with_highest_friction": {}
        }
        
        if not ledger_path.exists():
            print(f"  [FrictionObservatory] Ledger not found: {ledger_path}")
            return report

        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    ev = json.loads(line)
                    if ev.get("event") == "execution_blocked":
                        report["total_friction_events"] += 1
                        
                        f_type = ev.get("friction_type", "Unknown")
                        blocker = ev.get("blocker", "unknown_blocker")
                        env = ev.get("environment", "unknown_env")
                        
                        report["friction_by_type"][f_type] = report["friction_by_type"].get(f_type, 0) + 1
                        report["top_blockers"][blocker] = report["top_blockers"].get(blocker, 0) + 1
                        report["environments_with_highest_friction"][env] = report["environments_with_highest_friction"].get(env, 0) + 1
                        
        except Exception as e:
            print(f"  [FrictionObservatory] Error reading ledger: {e}")

        # Sort dictionaries by count (descending)
        report["friction_by_type"] = dict(sorted(report["friction_by_type"].items(), key=lambda item: item[1], reverse=True))
        report["top_blockers"] = dict(sorted(report["top_blockers"].items(), key=lambda item: item[1], reverse=True))
        report["environments_with_highest_friction"] = dict(sorted(report["environments_with_highest_friction"].items(), key=lambda item: item[1], reverse=True))
        
        try:
            report_path = Path(store_dir) / "top_runtime_frictions_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"  [FrictionObservatory] Generated: {report_path}")
        except Exception as e:
            print(f"  [FrictionObservatory] Failed to write report: {e}")
            
        return report
