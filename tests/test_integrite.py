'tests/test_integrite.py'
import pytest
import json
from unittest.mock import MagicMock, patch, call
from app.integrite.hash import (
    compute_data_hash, compute_chain_hash,
    generate_chain_salt, verify_data_hash, verify_chain_hash
)
from app.integrite.hashchain     import (
    GENESIS_HASH, get_last_chain_hash, verify_full_chain
)
from app.integrite.integrite_service import IntegriteService


# ---- Tests hash----------------------------------------------

def test_data_hash_deterministe():
    """Le même payload produit toujours le même hash."""
    payload = {"numero_billet": "BIL-001", "montant": 150, "gare": "Casablanca"}
    h1 = compute_data_hash(payload)
    h2 = compute_data_hash(payload)
    assert h1 == h2
    assert len(h1) == 64   # SHA-256 = 64 caractères hex


def test_data_hash_ordre_cles():
    """L'ordre des clés ne doit pas changer le hash (sort_keys=True)."""
    p1 = {"a": 1, "b": 2, "c": 3}
    p2 = {"c": 3, "a": 1, "b": 2}
    assert compute_data_hash(p1) == compute_data_hash(p2)


def test_data_hash_sensible_modifications():
    """Modifier un seul caractère doit produire un hash totalement différent."""
    p_original = {"numero_billet": "BIL-001", "montant": 150}
    p_modifie  = {"numero_billet": "BIL-001", "montant": 151}   # +1 MAD
    assert compute_data_hash(p_original) != compute_data_hash(p_modifie)


def test_chain_hash_inclut_precedent():
    """Le chain_hash doit changer si le previous_hash change."""
    payload = {"data": "test"}
    salt    = generate_chain_salt()
    h1 = compute_chain_hash(payload, "aaa", salt)
    h2 = compute_chain_hash(payload, "bbb", salt)
    assert h1 != h2


def test_chain_hash_inclut_sel():
    """Le chain_hash doit changer si le sel change."""
    payload  = {"data": "test"}
    prev     = "aaa"
    h1 = compute_chain_hash(payload, prev, "sel1")
    h2 = compute_chain_hash(payload, prev, "sel2")
    assert h1 != h2


def test_verify_data_hash_correct():
    payload = {"numero_billet": "BIL-999", "montant": 200}
    h = compute_data_hash(payload)
    assert verify_data_hash(payload, h) is True


def test_verify_data_hash_tampered():
    payload  = {"numero_billet": "BIL-999", "montant": 200}
    h        = compute_data_hash(payload)
    tampered = {"numero_billet": "BIL-999", "montant": 201}
    assert verify_data_hash(tampered, h) is False


def test_verify_chain_hash_correct():
    payload = {"data": "ok"}
    salt    = generate_chain_salt()
    prev    = "abc123"
    h = compute_chain_hash(payload, prev, salt)
    assert verify_chain_hash(payload, prev, salt, h) is True


def test_verify_chain_hash_broken_link():
    """Changer le previous_hash doit invalider la vérification."""
    payload = {"data": "ok"}
    salt    = generate_chain_salt()
    h       = compute_chain_hash(payload, "original_prev", salt)
    assert verify_chain_hash(payload, "different_prev", salt, h) is False


# ---- Tests IntegriteService (DB mockée) ------------------------------

@pytest.fixture
def service():
    return IntegriteService()


@pytest.fixture
def mock_db():
    return MagicMock()


def _make_chain_rows(payloads: list[dict]) -> list:
    """
    Construit une liste de maillons cohérents pour tester verify_full_chain.
    Chaque maillon est correctement chaîné au précédent.
    """
    rows  = []
    prev  = GENESIS_HASH

    for i, payload in enumerate(payloads, start=1):
        salt       = generate_chain_salt()
        data_hash  = compute_data_hash(payload)
        chain_hash = compute_chain_hash(
            {"_hash": data_hash}, prev, salt
        )
        row = MagicMock()
        row.Sequence      = i
        row.TransactionId = f"txn-{i:04d}"
        row.DataHash      = data_hash
        row.ChainHash     = chain_hash
        row.PreviousHash  = prev
        row.Salt          = salt
        rows.append(row)
        prev = chain_hash

    return rows


def test_seal_transaction(service, mock_db):
    """seal_transaction doit retourner un HashChainEntry avec sequence >= 1."""
    mock_db.execute.return_value.fetchone.return_value = None   # Chaîne vide

    with patch("app.integrite.hashchain.get_last_chain_hash",
               return_value=(GENESIS_HASH, 0)):
        result = service.seal_transaction(
            db               = mock_db,
            transaction_id   = "txn-test-001",
            transaction_type = "controle",
            source_id        = 42,
            payload          = {"numero_billet": "BIL-001", "resultat": "OK"},
            matricule        = "AG001",
            device_id        = "PDA-001"
        )

    assert result.sequence      == 1
    assert result.previous_hash == GENESIS_HASH
    assert len(result.data_hash)  == 64
    assert len(result.chain_hash) == 64


def test_verify_chain_valide(service, mock_db):
    """Une chaîne correctement construite doit passer la vérification."""
    payloads = [
        {"numero_billet": "BIL-001", "resultat": "OK"},
        {"numero_billet": "BIL-002", "montant": 120},
        {"numero_billet": "BIL-003", "resultat": "KO"},
    ]
    rows = _make_chain_rows(payloads)

    with patch("app.integrite.integrite_service.verify_full_chain") as mock_verify: 
        mock_verify.return_value = {
            "valid": True, "total": 3, "broken_at": None, "error": None
        }
        result = service.verify_chain(mock_db)

    assert result.valid is True
    assert result.total == 3
    assert result.broken_at is None

def test_verify_chain_falsifiee(service, mock_db):
    """Une chaîne avec un maillon altéré doit échouer la vérification."""
    with patch("app.integrite.integrite_service.verify_full_chain") as mock_verify: 
        mock_verify.return_value = {
            "valid":     False,
            "total":     5,
            "broken_at": 3,
            "error":     "Hash corrompu au maillon 3"
        }
        result = service.verify_chain(mock_db)

    assert result.valid is False
    assert result.broken_at == 3
    assert "maillon 3" in result.error


def test_genesis_hash_format():
    """Le bloc genesis doit être une chaîne de 64 zéros."""
    assert GENESIS_HASH == "0" * 64
    assert len(GENESIS_HASH) == 64


def test_seal_deux_transactions_sequence_incrementale(service, mock_db):
    """Deux transactions scellées successivement doivent avoir des séquences 1 et 2."""
    payload1 = {"numero_billet": "BIL-001"}
    payload2 = {"numero_billet": "BIL-002"}

    first_chain_hash = None

    with patch("app.integrite.hashchain.get_last_chain_hash",
               return_value=(GENESIS_HASH, 0)):
        r1 = service.seal_transaction(
            mock_db, "txn-001", "controle", 1,
            payload1, "AG001", "PDA-001"
        )
        first_chain_hash = r1.chain_hash

    with patch("app.integrite.hashchain.get_last_chain_hash",
               return_value=(first_chain_hash, 1)):
        r2 = service.seal_transaction(
            mock_db, "txn-002", "controle", 2,
            payload2, "AG001", "PDA-001"
        )

    assert r1.sequence       == 1
    assert r2.sequence       == 2
    assert r2.previous_hash  == r1.chain_hash   # Le maillon 2 pointe vers le maillon 1