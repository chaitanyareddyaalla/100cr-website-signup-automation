import pytest
from fastapi.testclient import TestClient

import backend.app.main as backend_main
from backend.app.main import (
    app,
    claim_next_available_identity,
    finalize_identity,
    mark_identity_processing,
    reserve_identity,
    seed_authorized_identities,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_main, "DATABASE_PATH", tmp_path / "lifecycle_test.db")
    backend_main.initialize_database()


def test_seed_identities_and_claim_lifecycle():
    # 1. Seed identities
    count = seed_authorized_identities(["ID-001", "ID-002", "ID-003"])
    assert count == 3

    # Cannot insert duplicates
    duplicate_count = seed_authorized_identities(["ID-001", "ID-004"])
    assert duplicate_count == 1

    # 2. Claim available identity
    claimed = claim_next_available_identity("batch-1")
    assert claimed == "ID-001"

    # Second claim gets next available
    claimed_2 = claim_next_available_identity("batch-1")
    assert claimed_2 == "ID-002"

    # 3. Mark processing
    mark_identity_processing("ID-001", "batch-1")

    # 4. Finalize identity
    finalize_identity("ID-001", "SUCCESS", "batch-1")
    finalize_identity("ID-002", "FAILED", "batch-1")

    # Claim third
    claimed_3 = claim_next_available_identity("batch-1")
    assert claimed_3 == "ID-003"
    finalize_identity("ID-003", "SKIPPED", "batch-1")

    # Claim fourth
    claimed_4 = claim_next_available_identity("batch-1")
    assert claimed_4 == "ID-004"

    # No more available identities
    claimed_none = claim_next_available_identity("batch-1")
    assert claimed_none is None


def test_reserve_identity_prevents_duplicate_reservations():
    assert reserve_identity("MANUAL-1", "batch-1") is True
    # Second reservation of same identifier should fail
    assert reserve_identity("MANUAL-1", "batch-2") is False


def test_seed_identities_endpoint():
    with TestClient(app) as client:
        response = client.post(
            "/identities/seed",
            json={"identifiers": ["API-IDENT-1", "API-IDENT-2"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["seeded"] == 2
        assert data["total_requested"] == 2
