import json
import os
import random
import copy
from pathlib import Path

# Base structures from simple forms
def create_login_template(site_idx):
    base_session = [
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/login",
            "step": 1,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "banner", "name": f"Header {site_idx}", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 1, "role": "main", "name": "Login Form", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 2, "role": "textbox", "name": f"Email Address {site_idx}", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 3, "role": "textbox", "name": f"Secret Password {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 4, "role": "button", "name": "Submit Login", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[1,2,"parent_child"], [1,3,"parent_child"], [1,4,"parent_child"], [2,3,"sibling"], [3,4,"sibling"]]
            },
            "expert_action": {
                "type": "open_url",
                "action_id": 0,
                "element_idx": -1,
                "url": f"https://app-{site_idx}.com/login"
            },
            "success": True
        },
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/login",
            "step": 2,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": f"Email Address {site_idx}", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": f"Secret Password {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Submit Login", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[0,1,"sibling"]]
            },
            "expert_action": {
                "type": "type",
                "action_id": 2,
                "element_idx": 0,
                "text": f"user_{site_idx}@example.com"
            },
            "success": True
        },
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/login",
            "step": 3,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": f"Email Address {site_idx}", "value": f"user_{site_idx}@example.com", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": f"Secret Password {site_idx}", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Submit Login", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[1,2,"sibling"]]
            },
            "expert_action": {
                "type": "type",
                "action_id": 2,
                "element_idx": 1,
                "text": "SimPwd" + str(site_idx)
            },
            "success": True
        },
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/login",
            "step": 4,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": f"Email Address {site_idx}", "value": f"user_{site_idx}@example.com", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": f"Secret Password {site_idx}", "value": "••••••••", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Submit Login", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": []
            },
            "expert_action": {
                "type": "click",
                "action_id": 1,
                "element_idx": 2
            },
            "success": True
        },
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/dashboard",
            "step": 5,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "heading", "name": f"Welcome User {site_idx}!", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 1, "role": "button", "name": "Sign Out Hub", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}
                ],
                "edges": []
            },
            "expert_action": {
                "type": "click",
                "action_id": 1,
                "element_idx": 1
            },
            "success": True
        },
        {
            "goal": f"login to application_v{site_idx}",
            "url": f"https://app-{site_idx}.com/logout",
            "step": 6,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "heading", "name": "You have been logged out", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}
                ],
                "edges": []
            },
            "expert_action": {
                "type": "done",
                "action_id": 7,
                "element_idx": -1
            },
            "success": True
        }
    ]
    return base_session

def create_social_template(site_idx):
    return [
        {
            "goal": f"navigate to feed on social_network_{site_idx} and extract trending",
            "url": f"https://social-{site_idx}.net/home",
            "step": 1,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "heading", "name": f"Trending Topic Alpha {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "heading", "name": f"Trending Topic Beta {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Like Post", "value": "", "focused": False, "depth": 3, "visible": True, "disabled": False}
                ],
                "edges": [[0,1,"sibling"], [1,2,"sibling"]]
            },
            "expert_action": {
                "type": "scroll",
                "action_id": 3,
                "element_idx": -1,
                "value": "down"
            },
            "success": True
        },
        {
            "goal": f"navigate to feed on social_network_{site_idx} and extract trending",
            "url": f"https://social-{site_idx}.net/home",
            "step": 2,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "heading", "name": f"Trending Topic Gamma {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "heading", "name": f"Trending Topic Delta {site_idx}", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": []
            },
            "expert_action": {
                "type": "extract",
                "action_id": 5,
                "element_idx": 0,
            },
            "success": True
        },
        {
            "goal": f"navigate to feed on social_network_{site_idx} and extract trending",
            "url": f"https://social-{site_idx}.net/home",
            "step": 3,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "button", "name": "Log out from Social", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}
                ],
                "edges": []
            },
            "expert_action": {
                "type": "click",
                "action_id": 1,
                "element_idx": 0,
            },
            "success": True
        },
        {
            "goal": f"navigate to feed on social_network_{site_idx} and extract trending",
            "url": f"https://social-{site_idx}.net/bye",
            "step": 4,
            "graph": {
                "nodes": [{"idx": 0, "role": "heading", "name": "Goodbye", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}],
                "edges": []
            },
            "expert_action": {
                "type": "done",
                "action_id": 7,
                "element_idx": -1,
            },
            "success": True
        }
    ]

def add_noise(session_data, site_idx):
    session = copy.deepcopy(session_data)
    noise_nodes = [
        {"idx": 90, "role": "banner", "name": f"Ad {random.randint(1,99)}", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
        {"idx": 91, "role": "contentinfo", "name": "Footer links", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
        {"idx": 92, "role": "navigation", "name": "Sitemap", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}
    ]
    for step in session:
        step["graph"]["nodes"].extend(noise_nodes)
    return session

def generate_500():
    save_dir = Path("training/massive_sessions")
    save_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating 500 massive synthetic variations...")
    
    for i in range(1, 501):
        if i % 2 == 0:
            session = create_login_template(i)
        else:
            session = create_social_template(i)
            
        # 30% chance to add noise nodes for robustness
        if random.random() < 0.3:
            session = add_noise(session, i)
            
        # Give random real-world sounding goals
        verbs = ["Login to", "Sign in to", "Access", "Authenticate into", "Use credentials for"]
        targets = ["client portal", "internal social feed", "dashboard", "intranet", "AWS clone"]
        if i % 2 == 0:
            goal_str = f"{random.choice(verbs)} {random.choice(targets)} site_{i}"
            for step in session:
                step["goal"] = goal_str

        filepath = save_dir / f"S_GOLD_SYN_MASSIVE_{i:04d}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
            
    print("Successfully generated 500 Golden Synthetic Sessions.")

if __name__ == "__main__":
    generate_500()
