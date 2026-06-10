import json
import os
from pathlib import Path

def generate_sample_login():
    """Manually crafted sample based on the Ultimate Prompt to bootstrap training."""
    session = [
        {
            "goal": "login to github with username and password",
            "url": "https://github.com/login",
            "step": 1,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "banner", "name": "Header", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 1, "role": "main", "name": "Login Form", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 2, "role": "textbox", "name": "Username or email address", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 3, "role": "textbox", "name": "Password", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 4, "role": "button", "name": "Sign in", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[1,2,"parent_child"], [1,3,"parent_child"], [1,4,"parent_child"], [2,3,"sibling"], [3,4,"sibling"]]
            },
            "expert_action": {
                "type": "open_url",
                "action_id": 0,
                "element_idx": -1,
                "url": "https://github.com/login"
            },
            "success": True
        },
        {
            "goal": "login to github with username and password",
            "url": "https://github.com/login",
            "step": 2,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "banner", "name": "Header", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 1, "role": "main", "name": "Login Form", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 2, "role": "textbox", "name": "Username or email address", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 3, "role": "textbox", "name": "Password", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 4, "role": "button", "name": "Sign in", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[1,2,"parent_child"], [1,3,"parent_child"], [1,4,"parent_child"]]
            },
            "expert_action": {
                "type": "wait",
                "action_id": 4,
                "element_idx": -1
            },
            "success": True
        },
        {
            "goal": "login to github with username and password",
            "url": "https://github.com/login",
            "step": 3,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": "Username or email address", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": "Password", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Sign in", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[0,1,"sibling"]]
            },
            "expert_action": {
                "type": "type",
                "action_id": 2,
                "element_idx": 0,
                "text": "browsermind_user"
            },
            "success": True
        },
        {
            "goal": "login to github with username and password",
            "url": "https://github.com/login",
            "step": 4,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": "Username or email address", "value": "browsermind_user", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": "Password", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Sign in", "value": "", "focused": False, "depth": 2, "visible": True, "disabled": False}
                ],
                "edges": [[1,2,"sibling"]]
            },
            "expert_action": {
                "type": "type",
                "action_id": 2,
                "element_idx": 1,
                "text": "secure_pass_123"
            },
            "success": True
        },
        {
            "goal": "login to github with username and password",
            "url": "https://github.com/login",
            "step": 5,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "textbox", "name": "Username or email address", "value": "browsermind_user", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 1, "role": "textbox", "name": "Password", "value": "••••••••", "focused": False, "depth": 2, "visible": True, "disabled": False},
                    {"idx": 2, "role": "button", "name": "Sign in", "value": "", "focused": True, "depth": 2, "visible": True, "disabled": False}
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
            "goal": "login to github with username and password",
            "url": "https://github.com/dashboard",
            "step": 6,
            "graph": {
                "nodes": [
                    {"idx": 0, "role": "heading", "name": "Dashboard", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False},
                    {"idx": 1, "role": "link", "name": "Profile", "value": "", "focused": False, "depth": 1, "visible": True, "disabled": False}
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
    return session

def save_synthetic_batch(name_prefix: str, count: int):
    save_dir = Path("training/massive_sessions")
    save_dir.mkdir(parents=True, exist_ok=True)
    
    for i in range(count):
        session = generate_sample_login()
        # Add slight variations (different goals, slightly different node names)
        if i > 0:
            session[0]["goal"] = f"sign in to account variation {i}"
        
        filepath = save_dir / f"S_SYN_{name_prefix}_{i:03d}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
            
    print(f"Saved {count} synthetic sessions to {save_dir}")

if __name__ == "__main__":
    save_synthetic_batch("login", 50)
