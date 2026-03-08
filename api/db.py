import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models import Base

load_dotenv()

# Read from environment at runtime to support config changes without restart
def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./agenttest.sqlite")


def get_engine():
    database_url = get_database_url()
    engine_kwargs = {"future": True}
    if not database_url.startswith("sqlite"):
        engine_kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **engine_kwargs)


engine = get_engine()
SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)
SessionLocal.configure(bind=engine)


def refresh_engine() -> None:
    global engine
    engine = get_engine()
    SessionLocal.configure(bind=engine)


def init_db() -> None:
    refresh_engine()
    Base.metadata.create_all(bind=engine)
