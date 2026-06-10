"""
Bootstrap: write pilot.json vault entry using the project's own persistence layer.
Run once from the project root: python _bootstrap_pilot_vault.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider

store_dir = str(Path.home() / ".browsermind")
provider = LocalJSONPersistenceProvider(store_dir)

_data = {
    "persona_name": "pilot",
    "secrets": {
        "saucedemo": {
            "username": "standard_user",
            "password": "secret_sauce"
        },
        "aria_internet": {
            "username": "tomsmith",
            "password": "SuperSecretPassword!"
        }
    },
    "resources": {}
}

provider.save("persona_vault", "pilot", _data)

# Verify round-trip
loaded = provider.load("persona_vault", "pilot")
assert loaded is not None, "FAIL: load returned None (checksum mismatch or missing file)"
assert loaded["secrets"]["saucedemo"]["password"] == "secret_sauce"
assert loaded["secrets"]["aria_internet"]["password"] == "SuperSecretPassword!"

print("OK: pilot.json written and verified")
print(f"    path: {store_dir}/persona_vault/pilot.json")
