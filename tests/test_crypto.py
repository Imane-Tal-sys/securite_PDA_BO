'test_crypto.py'
import pytest
import json
from unittest.mock import patch

from app.crypto.crypto_service import CryptoService
from app.crypto.aes import generate_aes_key, aes_encrypt, aes_decrypt
from app.crypto.rsa import generate_rsa_keypair, rsa_encrypt, rsa_decrypt, init_keys
from app.crypto.schemas import EncryptedPayload
from Crypto.PublicKey import RSA


@pytest.fixture(autouse=True)
def mock_keys_directory(tmp_path):
    """Isole les tests en mockant le répertoire des clés."""
    with patch("app.crypto.rsa.KEY_DIR", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def crypto():
    return CryptoService()


def test_aes_chiffrement_dechiffrement():
    cle = generate_aes_key()
    message = "Billet N° 12345 - Paris -> Lyon".encode('utf-8')
    chiffre = aes_encrypt(message, cle)
    assert "iv" in chiffre and "tag" in chiffre and "data" in chiffre
    assert chiffre["data"] != message
    dechiffre = aes_decrypt(chiffre, cle)
    assert dechiffre == message


def test_aes_detection_falsification():
    cle = generate_aes_key()
    chiffre = aes_encrypt("données sensibles".encode('utf-8'), cle)
    data_falsifiee = bytearray(chiffre["data"])
    data_falsifiee[0] ^= 0xFF
    chiffre_falsifie = {**chiffre, "data": bytes(data_falsifiee)}
    with pytest.raises(ValueError):
        aes_decrypt(chiffre_falsifie, cle)


def test_aes_iv_unique():
    cle = generate_aes_key()
    msg = b"meme message"
    c1 = aes_encrypt(msg, cle)
    c2 = aes_encrypt(msg, cle)
    assert c1["iv"] != c2["iv"]


def test_rsa_chiffrement_dechiffrement():
    priv_pem, pub_pem = generate_rsa_keypair()
    pub_key = RSA.import_key(pub_pem)
    priv_key = RSA.import_key(priv_pem)
    cle_aes = generate_aes_key()
    enc = rsa_encrypt(cle_aes, pub_key)
    dec = rsa_decrypt(enc, priv_key)
    assert dec == cle_aes


def test_rsa_mauvaise_cle():
    _, pub_pem = generate_rsa_keypair()
    priv_pem2, _ = generate_rsa_keypair()
    pub_key = RSA.import_key(pub_pem)
    priv_key2 = RSA.import_key(priv_pem2)
    cle_aes = generate_aes_key()
    enc = rsa_encrypt(cle_aes, pub_key)
    with pytest.raises((ValueError, KeyError, TypeError)):
        rsa_decrypt(enc, priv_key2)


def test_e2ee_flux_complet(crypto):
    payload_original = {
        "type": "controle",
        "numero_billet": "BIL-20260520-001",
        "gare_depart_id": 5,
        "resultat": "OK"
    }
    paquet = crypto.encrypt_payload(payload_original, device_id="PDA-001")
    assert paquet.transaction_id != ""
    assert paquet.device_id == "PDA-001"
    assert paquet.ciphertext != json.dumps(payload_original, ensure_ascii=False)
    payload_recu = crypto.decrypt_payload(paquet)
    assert payload_recu == payload_original


def test_e2ee_transaction_id_unique(crypto):
    payload = {"type": "vente", "montant": 150}
    p1 = crypto.encrypt_payload(payload, "PDA-001")
    p2 = crypto.encrypt_payload(payload, "PDA-001")
    assert p1.transaction_id != p2.transaction_id


def test_e2ee_payload_corrompu(crypto):
    payload = {"type": "controle", "numero_billet": "BIL-001"}
    paquet = crypto.encrypt_payload(payload, "PDA-001")
    # Corrompre le tag
    paquet_corrompu = EncryptedPayload(
        encrypted_key=paquet.encrypted_key,
        iv=paquet.iv,
        tag="corrupted_tag_data",
        ciphertext=paquet.ciphertext,
        device_id=paquet.device_id,
        transaction_id=paquet.transaction_id
    )
    with pytest.raises(ValueError):
        crypto.decrypt_payload(paquet_corrompu)


def test_e2ee_json_malforme(crypto):
    """Un payload avec un JSON invalide après déchiffrement doit lever ValueError."""
    # On utilise le crypto service pour générer les clés, mais on forge manuellement un ciphertext
    from app.crypto.aes import generate_aes_key, aes_encrypt
    from app.crypto.rsa import load_public_key, rsa_encrypt
    import base64

    # S'assurer que les clés existent (crypto les a déjà initialisées)
    aes_key = generate_aes_key()
    public_key = load_public_key()   # les clés existent grâce au fixture et à crypto
    encrypted_key = rsa_encrypt(aes_key, public_key)

    # JSON invalide
    invalid_json = b"{invalid json content"
    encrypted = aes_encrypt(invalid_json, aes_key)

    paquet = EncryptedPayload(
        encrypted_key=base64.b64encode(encrypted_key).decode("ascii"),
        iv=base64.b64encode(encrypted["iv"]).decode("ascii"),
        tag=base64.b64encode(encrypted["tag"]).decode("ascii"),
        ciphertext=base64.b64encode(encrypted["data"]).decode("ascii"),
        device_id="PDA-001",
        transaction_id="test-uuid"
    )

    with pytest.raises(ValueError):
        crypto.decrypt_payload(paquet)