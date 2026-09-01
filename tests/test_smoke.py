from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from archaeology.api.main import create_app
from archaeology.llm.tracing import trace_call
from archaeology.storage.base import Base
from archaeology.storage.models import Trace


def test_trace_call_roundtrip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = trace_call(session, stage="synthesis", model="sonnet-5", prompt="p", response="r")
        session.commit()
        fetched = session.execute(select(Trace)).scalar_one()
        assert fetched.id == row.id
        assert fetched.stage == "synthesis"
        assert fetched.model == "sonnet-5"


def test_healthz() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
