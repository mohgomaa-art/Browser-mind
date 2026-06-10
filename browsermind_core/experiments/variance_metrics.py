"""Variance Metrics Engine.

Implements algorithms to calculate distances between two recorded demonstrations.
"""
from typing import List, Dict, Any
import Levenshtein

def action_distance(demo1_actions: List[Dict], demo2_actions: List[Dict]) -> float:
    """
    Computes Edit Distance on the raw sequence of actions.
    An action is represented by (action_type, target_role, target_name).
    Returns normalized distance (0.0 = identical, 1.0 = completely different).
    """
    seq1 = [f"{a.get('action_type')}:{a.get('target_role')}:{a.get('target_name')}" for a in demo1_actions if a.get('action_type') != 'session']
    seq2 = [f"{a.get('action_type')}:{a.get('target_role')}:{a.get('target_name')}" for a in demo2_actions if a.get('action_type') != 'session']
    
    if not seq1 and not seq2:
        return 0.0
    
    dist = Levenshtein.distance(seq1, seq2)
    max_len = max(len(seq1), len(seq2))
    return dist / max_len if max_len > 0 else 0.0

def workflow_distance(tpl1_steps: List[Dict], tpl2_steps: List[Dict]) -> float:
    """
    Computes Edit Distance on the compiled workflow steps.
    This strips out captchas, redundant clicks, etc.
    Returns normalized distance (0.0 = identical, 1.0 = completely different).
    """
    seq1 = [f"{s.get('action_type')}:{s.get('target_role')}:{s.get('target_name')}" for s in tpl1_steps]
    seq2 = [f"{s.get('action_type')}:{s.get('target_role')}:{s.get('target_name')}" for s in tpl2_steps]
    
    if not seq1 and not seq2:
        return 0.0
        
    dist = Levenshtein.distance(seq1, seq2)
    max_len = max(len(seq1), len(seq2))
    return dist / max_len if max_len > 0 else 0.0

def state_path_distance(tpl1_steps: List[Dict], tpl2_steps: List[Dict]) -> float:
    """
    Computes Edit Distance on the sequence of contexts (e.g. Navigation steps).
    This tracks the high-level 'State Path' traversed during the workflow.
    Returns normalized distance (0.0 = identical, 1.0 = completely different).
    """
    # Use navigations as a proxy for major state transitions until intermediate state inference is built.
    seq1 = [f"nav:{s.get('url', '')}" for s in tpl1_steps if s.get('action_type') == 'navigate']
    seq2 = [f"nav:{s.get('url', '')}" for s in tpl2_steps if s.get('action_type') == 'navigate']
    
    if not seq1 and not seq2:
        return 0.0
        
    dist = Levenshtein.distance(seq1, seq2)
    max_len = max(len(seq1), len(seq2))
    return dist / max_len if max_len > 0 else 0.0

def state_achievement(s1_inferred: str, s2_inferred: str, s1_url: str, s2_url: str) -> float:
    """
    Returns 0.0 if Goal Achievement is identical, 1.0 if different.
    """
    if s1_inferred != "UNKNOWN" and s1_inferred == s2_inferred:
        return 0.0
    if s1_url and s1_url == s2_url:
        return 0.0
    return 1.0
