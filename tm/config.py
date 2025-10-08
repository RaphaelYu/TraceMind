import os

from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    data_dir: str = os.getenv("DATA_DIR", "./data")
    log_dir: str = os.getenv("LOG_DIR", None)  # default computed from data_dir
    batch_max: int = int(os.getenv("BATCH_MAX", "2000"))
    batch_ms: float = float(os.getenv("BATCH_MS", "0.006"))  # 6ms
    fsync_ms: float = float(os.getenv("FSYNC_MS", "0.050"))  # 50ms
    seg_bytes: int = int(os.getenv("SEG_BYTES", "134217728"))  # 128MB
    q_max: int = int(os.getenv("Q_MAX", "50000"))
    bind_host: str = os.getenv("BIND_HOST", "0.0.0.0")
    bind_port: int = int(os.getenv("BIND_PORT", "8443"))
    policy_mcp_url: Optional[str] = os.getenv("POLICY_MCP_URL")

    def effective_log_dir(self) -> str:
        return self.log_dir or (self.data_dir.rstrip("/") + "/eventlog")
