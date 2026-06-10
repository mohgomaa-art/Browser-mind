import subprocess
import time
import os
from pathlib import Path

sites = [
    "static_baseline",
    "saucedemo",
    "demoqa",
    "aria_internet",
    "github",
    "huggingface"
]

ITERATIONS = 4

print(f"Starting Dataset V3 generation...")
print(f"Running {ITERATIONS} iterations of {len(sites)} sites...")

for i in range(ITERATIONS):
    print(f"\n{'='*50}")
    print(f" ITERATION {i+1} / {ITERATIONS}")
    print(f"{'='*50}")
    
    for site in sites:
        print(f"\n--- Running site: {site} ---")
        try:
            env = os.environ.copy()
            env["BM_VAULT_PENDING_VAULT_EXTRACTION"] = "SuperSecretPassword!"
            env["PYTHONIOENCODING"] = "utf-8"
            
            subprocess.run(
                ["python", "scripts/auto_record.py", "run", "--site", site],
                check=True,
                env=env
            )
        except Exception as e:
            print(f"Failed {site}: {e}")
            
    time.sleep(2)
    
print("\nDataset V3 Generation Complete!")
print("Aggregating results...")
subprocess.run(["python", "scripts/aggregate_ledger.py"], env={"PYTHONIOENCODING": "utf-8", "PATH": __import__('os').environ["PATH"]})
