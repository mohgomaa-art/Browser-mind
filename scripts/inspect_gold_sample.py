"""Quick inspector: dump node names from first gold sample."""
import json, os, glob

gold_dir = os.path.join(os.path.dirname(__file__), '..', 'training', 'gold_interaction')
files = sorted(glob.glob(os.path.join(gold_dir, '*.json')))

if not files:
    print("No gold samples found")
    exit()

# Inspect first sample
with open(files[0], 'r', encoding='utf-8') as f:
    d = json.load(f)

print(f"URL: {d['url']}")
print(f"Goal: {d['goal']}")
print(f"State Family: {d['state_family_data']['state_family']}")
print(f"Task Type: {d['task_type']}")
print()
print(f"{'idx':>4s} {'role':>12s} {'name':<60s}")
print("-" * 80)
for n in d['ax_graph']['nodes']:
    print(f"{n['idx']:4d} {n['role']:>12s} {n.get('name','')[:60]:<60s}")
