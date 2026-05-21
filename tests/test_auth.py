'test_auth.py'
import pytest
from unittest.mock import MagicMock, patch
from app.auth.auth_service     import AuthService
from app.auth.password import generate_salt, hash_password, verify_password
from app.auth.session  import create_session, verify_token
from app.auth.device  import is_device_registered
from app.auth.schemas          import LoginRequest, ChangePasswordRequest
from fastapi                   import HTTPException


# ---- Tests Password ---------------------------------------------------

def test_hash_et_verification():
    """Le mot de passe hashé doit être vérifiable."""
    salt = generate_salt()
    h    = hash_password("MonMdp123!", salt)
    assert verify_password("MonMdp123!", salt, h) is True
    assert verify_password("MauvaisMdp", salt, h) is False


def test_sel_unique():
    """Deux sels générés ne doivent jamais être identiques."""
    s1, s2 = generate_salt(), generate_salt()
    assert s1 != s2


def test_meme_mdp_sel_different_hash_different():
    """Même mot de passe + sel différent = hash différent."""
    s1, s2 = generate_salt(), generate_salt()
    h1 = hash_password("MotDePasse", s1)
    h2 = hash_password("MotDePasse", s2)
    assert h1 != h2


# ---- Tests Session ---------------------------------------------------

def test_creation_et_verification_session():
    """Un token créé doit être vérifiable et contenir le bon matricule."""
    session = create_session("AG001", role_id=2, device_id="PDA-001")

    assert "access_token"  in session
    assert "session_key"   in session
    assert "expires_at"    in session

    payload = verify_token(session["access_token"])
    assert payload["sub"]       == "AG001"
    assert payload["device_id"] == "PDA-001"
    assert payload["role_id"]   == 2


def test_session_key_unique():
    """Deux sessions doivent avoir des clés AES différentes."""
    s1 = create_session("AG001", 1, "PDA-001")
    s2 = create_session("AG001", 1, "PDA-001")
    assert s1["session_key"] != s2["session_key"]


def test_token_invalide():
    """Un token falsifié doit lever une exception."""
    import jwt
    with pytest.raises(jwt.InvalidTokenError):
        verify_token("token.faux.invalide")


# ---- Tests AuthService (avec DB mockée) ------------------------------

@pytest.fixture
def mock_db():
    """Base de données mockée pour les tests unitaires."""
    return MagicMock()


@pytest.fixture
def auth_service():
    return AuthService()


def _make_user(
    mdp="Agent123!",
    etat=1,
    attempts=0,
    first_login=0
):
    """Construit un utilisateur de test avec le bon format de mot de passe."""
    salt   = generate_salt()
    hashed = hash_password(mdp, salt)
    return {
        "UtilisateurId":              1,
        "Matricule":                  "AG001",
        "Nom":                        "Ben Ali",
        "Prenom":                     "Youssef",
        "Password":                   f"{salt}${hashed}",
        "Etat":                       etat,
        "IsFirstConnexion":           first_login,
        "RoleId":                     2,
        "StatutUtilisateurId":        1,
        "ConnectionAttemptsNumber":   attempts,
        "LastConnectionAttemptDate":  None,
    }


def test_login_succes(auth_service, mock_db):
    """Login réussi → LoginResponse avec token et session_key."""
    user = _make_user()
    auth_service._get_user = MagicMock(return_value=user)
    auth_service._reset_attempts          = MagicMock()
    auth_service._update_last_connection  = MagicMock()

    with patch("app.auth.auth_service.is_device_registered", return_value=True):
        req  = LoginRequest(matricule="AG001", password="Agent123!", device_id="PDA-001")
        resp = auth_service.login(req, mock_db)

    assert resp.access_token != ""
    assert resp.session_key  != ""
    assert resp.is_first_login is False


def test_login_mauvais_mdp(auth_service, mock_db):
    """Mauvais mot de passe → HTTP 401 + compteur incrémenté."""
    user = _make_user()
    auth_service._get_user         = MagicMock(return_value=user)
    auth_service._increment_attempts = MagicMock()

    with pytest.raises(HTTPException) as exc:
        req = LoginRequest(matricule="AG001", password="MauvaisMdp", device_id="PDA-001")
        auth_service.login(req, mock_db)

    assert exc.value.status_code == 401
    auth_service._increment_attempts.assert_called_once()


def test_login_compte_bloque(auth_service, mock_db):
    """Compte avec 3 tentatives → HTTP 403."""
    user = _make_user(attempts=3)
    auth_service._get_user = MagicMock(return_value=user)

    with pytest.raises(HTTPException) as exc:
        req = LoginRequest(matricule="AG001", password="Agent123!", device_id="PDA-001")
        auth_service.login(req, mock_db)

    assert exc.value.status_code == 403
    assert "bloqué" in exc.value.detail


def test_login_device_non_autorise(auth_service, mock_db):
    """Device non enregistré → HTTP 403."""
    user = _make_user()
    auth_service._get_user        = MagicMock(return_value=user)
    auth_service._increment_attempts = MagicMock()

    with patch("app.auth.auth_service.is_device_registered", return_value=False):
        with pytest.raises(HTTPException) as exc:
            req = LoginRequest(matricule="AG001", password="Agent123!", device_id="PDA-INCONNU")
            auth_service.login(req, mock_db)

    assert exc.value.status_code == 403
    assert "Terminal" in exc.value.detail


def test_login_compte_inactif(auth_service, mock_db):
    """Compte désactivé (Etat=0) → HTTP 403."""
    user = _make_user(etat=0)
    auth_service._get_user = MagicMock(return_value=user)

    with pytest.raises(HTTPException) as exc:
        req = LoginRequest(matricule="AG001", password="Agent123!", device_id="PDA-001")
        auth_service.login(req, mock_db)

    assert exc.value.status_code == 403
    assert "désactivé" in exc.value.detail


def test_changement_mdp(auth_service, mock_db):
    """Changement de mot de passe réussi → success=True."""
    user = _make_user()
    auth_service._get_user = MagicMock(return_value=user)
    mock_db.execute = MagicMock()
    mock_db.commit  = MagicMock()

    req    = ChangePasswordRequest(
        matricule="AG001",
        old_password="Agent123!",
        new_password="NouveauMdp456!",
        device_id="PDA-001"
    )
    result = auth_service.change_password(req, mock_db)
    assert result["success"] is True