import pytest
import asyncio
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

from app.degradedMode.local_db     import init_local_db, get_connection
from app.degradedMode.buffer_store import (
    push_transaction, get_pending_transactions,
    mark_synchronized, increment_retry,
    get_pending_count, get_failed_transactions
)
from app.degradedMode.sync_service    import SyncService
from app.degradedMode.degradedMode_service import DegradedService


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Crée une base SQLite temporaire pour chaque test."""
    db_path = str(tmp_path / "test_buffer.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    init_local_db()
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


def make_packet(txn_id: str = "txn-001") -> dict:
    return {
        "encrypted_key":  "AAAA==",
        "iv":             "BBBB==",
        "tag":            "CCCC==",
        "ciphertext":     "DDDD==",
        "device_id":      "PDA-001",
        "transaction_id": txn_id
    }


# -----------------------------------------------------------------------
# Tests buffer_store
# -----------------------------------------------------------------------

def test_push_et_recuperation():
    """Une transaction poussée doit être récupérable en pending."""
    push_transaction("txn-001", "controle", make_packet("txn-001"))
    pending = get_pending_transactions()
    assert len(pending)              == 1
    assert pending[0]["transaction_id"] == "txn-001"
    assert pending[0]["operation_type"] == "controle"


def test_ordre_fifo():
    """Les transactions doivent être récupérées dans l'ordre d'insertion."""
    for i in range(5):
        push_transaction(f"txn-{i:03d}", "controle", make_packet(f"txn-{i:03d}"))

    pending = get_pending_transactions()
    ids = [p["transaction_id"] for p in pending]
    assert ids == ["txn-000", "txn-001", "txn-002", "txn-003", "txn-004"]


def test_mark_synchronized():
    """Après mark_synchronized, la transaction ne doit plus apparaître en pending."""
    local_id = push_transaction("txn-sync", "vente", make_packet("txn-sync"))
    assert get_pending_count() == 1

    mark_synchronized(local_id)
    assert get_pending_count() == 0

    pending = get_pending_transactions()
    assert len(pending) == 0


def test_increment_retry_exclut_apres_max():
    """Une transaction avec retry_count >= MAX_RETRY ne doit plus apparaître."""
    from app.degradedMode.buffer_store import MAX_RETRY
    local_id = push_transaction("txn-fail", "controle", make_packet("txn-fail"))

    for i in range(MAX_RETRY):
        increment_retry(local_id, f"Erreur {i}")

    pending = get_pending_transactions()
    assert len(pending) == 0   # Exclue car retry_count >= MAX_RETRY

    failed = get_failed_transactions()
    assert len(failed)         == 1
    assert failed[0]["transaction_id"] == "txn-fail"


def test_uuid_unique_requis():
    """Deux transactions avec le même transaction_id doivent lever une erreur."""
    import sqlite3
    push_transaction("txn-dup", "controle", make_packet("txn-dup"))
    with pytest.raises(sqlite3.IntegrityError):
        push_transaction("txn-dup", "controle", make_packet("txn-dup"))


def test_pending_count():
    """get_pending_count doit retourner le bon nombre."""
    assert get_pending_count() == 0
    push_transaction("txn-a", "controle", make_packet("txn-a"))
    push_transaction("txn-b", "vente",    make_packet("txn-b"))
    assert get_pending_count() == 2


# -----------------------------------------------------------------------
# Tests SyncService
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_succes():
    """La synchronisation doit marquer les transactions comme synchronized."""
    push_transaction("txn-s1", "controle", make_packet("txn-s1"))
    push_transaction("txn-s2", "vente",    make_packet("txn-s2"))

    svc = SyncService(jwt_token="fake-token")

    with patch.object(svc, "_send_transaction", return_value=(True, "")):
        result = await svc.sync_pending()

    assert result.sent_ok    == 2
    assert result.sent_failed == 0
    assert get_pending_count() == 0


@pytest.mark.asyncio
async def test_sync_echec_partiel():
    push_transaction("txn-ok",  "controle", make_packet("txn-ok"))
    push_transaction("txn-err", "vente",    make_packet("txn-err"))

    svc = SyncService(jwt_token="fake-token")

    async def mock_send(txn):
        return (True, "") if txn["transaction_id"] == "txn-ok" else (False, "Timeout serveur")

    from app.degradedMode.buffer_store import MAX_RETRY
    with patch("app.degradedMode.buffer_store.MAX_RETRY", 1):
        with patch.object(svc, "_send_transaction", side_effect=mock_send):
            result = await svc.sync_pending()
        # Vérification à l'intérieur du patch (MAX_RETRY = 1)
        pending = get_pending_transactions()
        assert len(pending) == 0
        failed = get_failed_transactions()
        assert len(failed) == 1

    assert result.sent_ok == 1
    assert result.sent_failed == 1


@pytest.mark.asyncio
async def test_sync_verrou_double():
    """Deux synchronisations simultanées : la seconde doit être ignorée."""
    svc = SyncService(jwt_token="fake-token")
    svc._syncing = True   # Simule une sync déjà en cours

    result = await svc.sync_pending()
    assert "déjà en cours" in result.errors[0]


# -----------------------------------------------------------------------
# Tests DegradedService
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_online_succes():
    """En mode en ligne, submit_operation doit envoyer directement."""
    svc = DegradedService()

    with patch.object(svc._monitor, "force_check", return_value=True):
        with patch.object(
            svc, "_send_direct",
            return_value={"mode": "online", "success": True, "buffered": False}
        ):
            result = await svc.submit_operation(
                "controle", "txn-online", make_packet("txn-online"),
                "/operations/controle/chiffre", "token"
            )

    assert result["mode"]    == "online"
    assert result["buffered"] is False


@pytest.mark.asyncio
async def test_submit_offline_buffer():
    """En mode hors ligne, submit_operation doit stocker localement."""
    svc = DegradedService()

    with patch.object(svc._monitor, "force_check", return_value=False):
        result = await svc.submit_operation(
            "controle", "txn-offline", make_packet("txn-offline"),
            "/operations/controle/chiffre", "token"
        )

    assert result["mode"]    == "offline"
    assert result["buffered"] is True
    assert get_pending_count() == 1


@pytest.mark.asyncio
async def test_submit_online_fallback_buffer():
    """Si l'envoi direct échoue, doit basculer automatiquement vers le tampon."""
    svc = DegradedService()

    async def mock_send_direct(*args, **kwargs):
        return svc._store_locally("controle", "txn-fallback", make_packet("txn-fallback"))

    with patch.object(svc._monitor, "force_check", return_value=True):
        with patch.object(svc, "_send_direct", side_effect=mock_send_direct):
            result = await svc.submit_operation(
                "controle", "txn-fallback", make_packet("txn-fallback"),
                "/operations/controle/chiffre", "token"
            )

    assert result["buffered"] is True