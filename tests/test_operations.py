'test_operations.py'
import pytest
from unittest.mock import MagicMock, patch
from datetime      import datetime, timezone

from app.operations.controle_service import ControleService
from app.operations.vente_service    import VenteService
from app.operations.payload_builder  import build_controle_payload, build_vente_payload
from app.operations.schemas          import ControleRequest, VenteRequest, OperationPayload
from app.operations.anti_replay      import is_duplicate_transaction
from fastapi import HTTPException


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Simule le retour d'un ControleId = 42 après INSERT
    db.execute.return_value.fetchone.return_value = (42,)
    db.commit = MagicMock()
    return db


@pytest.fixture
def controle_svc():
    return ControleService()


@pytest.fixture
def vente_svc():
    return VenteService()


def make_controle_payload(
    mission_id=1,
    numero_billet="BIL-001",
    resultat="OK",
    type_ctrl="BO"
) -> OperationPayload:
    return OperationPayload(
        operation_type = "controle",
        transaction_id = "txn-ctrl-0001",
        timestamp      = datetime.now(timezone.utc).isoformat(),
        device_id      = "PDA-001",
        matricule      = "AG001",
        data           = {
            "mission_id":         mission_id,
            "numero_billet":      numero_billet,
            "resultat_controle":  resultat,
            "type_controle":      type_ctrl,
            "date_heure_controle": datetime.now(timezone.utc).isoformat(),
        }
    )


def make_vente_payload(
    mission_id=1,
    montant=150.0,
    nb_voyageurs=1
) -> OperationPayload:
    return OperationPayload(
        operation_type = "vente",
        transaction_id = "txn-vente-0001",
        timestamp      = datetime.now(timezone.utc).isoformat(),
        device_id      = "PDA-001",
        matricule      = "AG001",
        data           = {
            "mission_id":        mission_id,
            "liaison_id":        10,
            "niveau_confort_id": 2,
            "niveau_prix_id":    1,
            "bareme_id":         1,
            "gamme_id":          None,
            "montant":           montant,
            "nombre_voyageurs":  nb_voyageurs,
            "titre_reduction":   "PLEIN_TARIF",
            "motif":             "NORMAL",
            "numero_motif":      "NM001",
            "date_operation":    datetime.now(timezone.utc).isoformat(),
        }
    )


# -----------------------------------------------------------------------
# Tests payload_builder
# -----------------------------------------------------------------------

def test_build_controle_payload_uuid_unique():
    """Deux appels successifs doivent générer des transaction_id différents."""
    req = ControleRequest(
        mission_id=1, numero_billet="BIL-001",
        device_id="PDA-001", matricule="AG001"
    )
    p1 = build_controle_payload(req, "AG001", "PDA-001")
    p2 = build_controle_payload(req, "AG001", "PDA-001")
    assert p1.transaction_id != p2.transaction_id


def test_build_vente_payload_contient_numero_transaction():
    """Le payload de vente doit contenir un numero_transaction."""
    req = VenteRequest(
        mission_id=1, liaison_id=10, niveau_confort_id=2,
        niveau_prix_id=1, bareme_id=1, montant=200,
        nombre_voyageurs=2, titre_reduction="PLEIN_TARIF",
        motif="NORMAL", numero_motif="NM001",
        device_id="PDA-001", matricule="AG001"
    )
    payload = build_vente_payload(req, "AG001", "PDA-001")
    assert "numero_transaction" in payload.data
    assert payload.data["numero_transaction"].startswith("TXN-")


# -----------------------------------------------------------------------
# Tests ControleService
# -----------------------------------------------------------------------

def test_controle_succes(controle_svc, mock_db):
    payload = make_controle_payload()
    with patch("app.operations.controle_service.assert_not_duplicate"):
        with patch.object(
            controle_svc.integrite_service, "seal_transaction",  
            return_value=MagicMock(sequence=1)
        ):
            resp = controle_svc.process_controle(payload, mock_db)
    assert resp.success is True
    assert resp.controle_id == 42

def test_controle_sans_mission_id(controle_svc, mock_db):
    """Un contrôle sans mission_id doit lever HTTP 422."""
    payload      = make_controle_payload()
    payload.data = {**payload.data, "mission_id": None}

    with patch("app.operations.controle_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            controle_svc.process_controle(payload, mock_db)
    assert exc.value.status_code == 422


def test_controle_resultat_invalide(controle_svc, mock_db):
    """Un résultat de contrôle inconnu doit lever HTTP 422."""
    payload = make_controle_payload(resultat="XX")

    with patch("app.operations.controle_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            controle_svc.process_controle(payload, mock_db)
    assert exc.value.status_code == 422
    assert "resultat_controle" in exc.value.detail


def test_controle_sans_billet_ni_code2d(controle_svc, mock_db):
    """Ni numero_billet ni code_2d → HTTP 422."""
    payload      = make_controle_payload()
    payload.data = {**payload.data, "numero_billet": None, "code_2d_controle": None}

    with patch("app.operations.controle_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            controle_svc.process_controle(payload, mock_db)
    assert exc.value.status_code == 422


# -----------------------------------------------------------------------
# Tests VenteService
# -----------------------------------------------------------------------

def test_vente_succes(vente_svc, mock_db):
    payload = make_vente_payload()
    with patch("app.operations.vente_service.assert_not_duplicate"):
        with patch.object(
            vente_svc.integrite_service, "seal_transaction",      
            return_value=MagicMock(sequence=2)
        ):
            resp = vente_svc.process_vente(payload, mock_db)
    assert resp.success is True
    assert resp.numero_billet.startswith("BIL-")

def test_vente_montant_negatif(vente_svc, mock_db):
    """Un montant négatif doit lever HTTP 422."""
    payload = make_vente_payload(montant=-50)

    with patch("app.operations.vente_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            vente_svc.process_vente(payload, mock_db)
    assert exc.value.status_code == 422
    assert "montant" in exc.value.detail


def test_vente_nb_voyageurs_zero(vente_svc, mock_db):
    """nombre_voyageurs = 0 doit lever HTTP 422."""
    payload = make_vente_payload(nb_voyageurs=0)

    with patch("app.operations.vente_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            vente_svc.process_vente(payload, mock_db)
    assert exc.value.status_code == 422


def test_vente_montant_incoherent(vente_svc, mock_db):
    """1 MAD pour 10 voyageurs = incohérent → HTTP 422."""
    payload = make_vente_payload(montant=1, nb_voyageurs=10)

    with patch("app.operations.vente_service.assert_not_duplicate"):
        with pytest.raises(HTTPException) as exc:
            vente_svc.process_vente(payload, mock_db)
    assert exc.value.status_code == 422


# -----------------------------------------------------------------------
# Tests Anti-rejeu
# -----------------------------------------------------------------------

def test_anti_rejeu_doublon(mock_db):
    """Un UUID déjà présent dans HashChain doit être détecté comme doublon."""
    mock_db.execute.return_value.fetchone.return_value = MagicMock(cnt=1)
    assert is_duplicate_transaction(mock_db, "txn-deja-vu") is True


def test_anti_rejeu_nouveau(mock_db):
    """Un UUID jamais vu doit passer."""
    mock_db.execute.return_value.fetchone.return_value = MagicMock(cnt=0)
    assert is_duplicate_transaction(mock_db, "txn-nouveau") is False


def test_numero_billet_format(vente_svc):
    """Le numéro de billet généré doit respecter le format BIL-YYYYMMDD-XXXXXXXX."""
    nb = vente_svc._generate_numero_billet()
    parts = nb.split("-")
    assert len(parts) == 3
    assert parts[0] == "BIL"
    assert len(parts[1]) == 8    # YYYYMMDD
    assert len(parts[2]) == 8    # 8 chars hex majuscule