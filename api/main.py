from fastapi import FastAPI
from pydantic import BaseModel
from shared.types import RunCreate
from worker.runner import run_backtest

app = FastAPI(title="agenttest")


class Health(BaseModel):
    ok: bool = True


@app.get("/health", response_model=Health)
def health():
    return Health()


@app.post("/runs")
def create_run(req: RunCreate):
    # MVP: run inline; later: enqueue to worker
    result = run_backtest(
        strategy_path=req.strategy_path,
        dataset_dir=req.dataset_dir,
        dataset_version=req.dataset_version,
        params=req.params,
    )
    return result.model_dump()
