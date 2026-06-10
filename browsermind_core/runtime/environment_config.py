"""
Environment Family / Instance config for pilot and recorder runs.
See DOCS/ENVIRONMENT_CONTRACT.md — profile_path is per (persona, Environment Instance).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import warnings


@dataclass(frozen=True)
class EnvironmentInstanceConfig:
    family_key: str
    origin: str
    start_url: str
    label: str

    def profile_dir(self, store_dir: Path | str, persona_name: Optional[str] = None) -> Path:
        base = Path(store_dir)
        if persona_name is None:
            warnings.warn(
                "EnvironmentInstanceConfig.profile_dir() called without persona_name; "
                "Chrome profile will be shared across personas. Pass persona_name to enforce isolation.",
                RuntimeWarning,
                stacklevel=2,
            )
            return base / "profiles" / self.family_key
        safe_persona = persona_name.lower().replace(" ", "_")
        return base / "profiles" / safe_persona / self.family_key


INSTANCES: Dict[str, EnvironmentInstanceConfig] = {
    "saucedemo": EnvironmentInstanceConfig(
        family_key="saucedemo",
        origin="https://www.saucedemo.com",
        start_url="https://www.saucedemo.com/",
        label="Sauce Demo (P1 smoke)",
    ),
    "facebook": EnvironmentInstanceConfig(
        family_key="facebook",
        origin="https://www.facebook.com",
        start_url="https://www.facebook.com/",
        label="Facebook",
    ),
}


def get_instance(key: str) -> EnvironmentInstanceConfig:
    if key not in INSTANCES:
        known = ", ".join(sorted(INSTANCES))
        raise KeyError(f"Unknown environment instance '{key}'. Known: {known}")
    return INSTANCES[key]
