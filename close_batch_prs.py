#!/usr/bin/env python3
"""Close all batch PRs (#1620-#1662) that have no real implementation."""
import os, json, subprocess, time

TOKEN = ""
cred_file = os.path.expanduser("~/.git-credentials")
if os.path.exists(cred_file):
    with open(cred_file) as f:
        for line in f:
            if "github.com" in line:
                t = line.split("://")[1].split("@")[0]
                TOKEN = t.split(":")[1] if ":" in t else t
if not TOKEN: TOKEN = os.environ.get("GH_TOKEN", "")
if not TOKEN: print("NO TOKEN"); exit(1)

API = "https://api.github.com/repos/orchestration-agent/AgentOrchestration"

def gh_api(method, path, data=None):
    url = f"{API}/{path}"
    h = f'curl -s -L -X {method} "{url}" -H "Authorization: token {TOKEN}" -H "Accept: application/vnd.github.v3+json"'
    if data: h += f" -d '{json.dumps(data)}'"
    return json.loads(subprocess.run(h, shell=True, capture_output=True, text=True, timeout=30).stdout)

# Get all open PRs by onchito-walks
prs_data = gh_api("GET", "pulls?state=open&per_page=100")
prs = prs_data if isinstance(prs_data, list) else []

# Filter to batch PRs (#1620-#1662) which have no unique implementation
# These have identical +56/-417 diffs (infra fixes only)
batch_prs = [p for p in prs if 1620 <= p["number"] <= 1662]
batch_prs.sort(key=lambda x: x["number"])

print(f"Batch PRs to close: {len(batch_prs)} from #{batch_prs[0]['number']} to #{batch_prs[-1]['number']}")

# Also identify which PRs have REAL implementations (manual ones)
good_pr_numbers = [1000, 1360, 1595, 1596, 1598, 1599, 1615, 1616]
good_prs = [p for p in prs if p["number"] in good_pr_numbers]
print(f"Good PRs to keep: {[p['number'] for p in good_prs]}")

# Close all batch PRs
closed = 0
for pr in batch_prs:
    result = gh_api("PATCH", f"pulls/{pr['number']}", {"state": "closed"})
    if result.get("state") == "closed":
        closed += 1
    else:
        print(f"  FAILED to close #{pr['number']}: {result.get('message','?')}")
    
    if closed % 10 == 0:
        print(f"  Closed {closed}/{len(batch_prs)}...")
        time.sleep(2)

print(f"\nClosed {closed}/{len(batch_prs)} batch PRs")
print(f"Kept {len(good_prs)} good PRs")

# Also delete the remote branches to clean up
print("\nCleaning remote branches...")
for pr in batch_prs:
    branch = pr.get("head", {}).get("ref", "")
    if branch:
        subprocess.run(
            f"cd /home/hermes/bounties/AgentOrchestration && git push origin -d {branch} 2>/dev/null",
            shell=True, capture_output=True, timeout=10
        )

print("\nDONE. Now re-implementing top 10 remaining bounties properly.")
