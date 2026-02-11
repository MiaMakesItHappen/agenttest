import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models import Base

load_dotenv()

# Default to local SQLite for no-Docker development.
# Override with Postgres in env when needed.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agenttest.sqlite")

engine_kwargs = {"future": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
