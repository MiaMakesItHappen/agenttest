from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class RunCreate(BaseModel):
    strategy_path: str = Field(..., description="Path to a python strategy file")
    dataset_dir: str
    dataset_version: str = "v1"
    params: Dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    dataset_version: str
    dataset_hash: str
    code_hash: str
    config_hash: str
    metrics: Dict[str, Any]
    artifacts_dir: Optional[str] = None
