"""One-shot script: compute checksum and write pilot.json to the persona_vault."""
import json
import hashlib
import os
from pathlib import Path

store_dir = Path.home() / ".browsermind"
vault_dir = store_dir / "persona_vault"
vault_dir.mkdir(parents=True, exist_ok=True)

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

raw = json.dumps(_data, sort_keys=True)
checksum = hashlib.sha256(raw.encode()).hexdigest()
payload = {"_checksum": checksum, "_data": _data}

out_path = vault_dir / "pilot.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

print(f"Written: {out_path}")
print(f"Checksum: {checksum}")

# Verify round-trip: load and check
with open(out_path, "r", encoding="utf-8") as f:
    loaded = json.load(f)

expected = loaded["_checksum"]
actual = hashlib.sha256(json.dumps(loaded["_data"], sort_keys=True).encode()).hexdigest()
if expected == actual:
    print("VERIFY: checksum OK")
else:
    print(f"VERIFY FAILED: expected={expected} actual={actual}")
    raise SystemExit(1)

data = loaded["_data"]
assert data["secrets"]["saucedemo"]["password"] == "secret_sauce", "saucedemo password mismatch"
assert data["secrets"]["aria_internet"]["password"] == "SuperSecretPassword!", "aria_internet password mismatch"
print("VERIFY: credential keys present and correct")
