from __future__ import annotations
from pathlib import Path
from config import DATA_DIR

def data_root() -> Path:
    p = Path(DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p

def server_dir(guild_id: int) -> Path:
    p = data_root() / "servers" / str(guild_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

def server_db_path(guild_id: int) -> Path:
    return server_dir(guild_id) / "server.db"
