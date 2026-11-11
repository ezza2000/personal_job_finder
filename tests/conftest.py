import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401
from app.db.base import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
