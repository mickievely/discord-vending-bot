from __future__ import annotations
from config import ROOT_USER_IDS

def is_root(user_id: int) -> bool:
    try:
        uid = int(user_id)
    except Exception:
        return False
    return uid in ROOT_USER_IDS
