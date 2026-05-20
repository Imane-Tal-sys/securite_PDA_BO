'rsa.py'
import os
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256

KEY_DIR = "keys"
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "private_key.pem")
PUBLIC_KEY_PATH  = os.path.join(KEY_DIR, "public_key.pem")


def generate_rsa_keypair() -> tuple[bytes, bytes]:
    """
    Génère une paire de clés RSA-2048.
    Retourne (clé_privée_pem, clé_publique_pem).
    RSA-2048 = 2048 bits → suffisant pour chiffrer une clé AES de 32 bytes.
    """
    key = RSA.generate(2048)
    private_key_pem = key.export_key()           # Format PEM, PKCS#1
    public_key_pem  = key.publickey().export_key()
    return private_key_pem, public_key_pem


def save_keypair(private_pem: bytes, public_pem: bytes) -> None:
    """Sauvegarde les clés sur disque (le dossier keys/ est dans .gitignore)."""
    os.makedirs(KEY_DIR, exist_ok=True)
    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_pem)
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_pem)
    print(f"[RSA] Clés sauvegardées dans {KEY_DIR}/")


def load_public_key() -> RSA.RsaKey:
    """Charge la clé publique depuis le disque."""
    with open(PUBLIC_KEY_PATH, "rb") as f:
        return RSA.import_key(f.read())


def load_private_key() -> RSA.RsaKey:
    """Charge la clé privée depuis le disque (Back-Office uniquement)."""
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return RSA.import_key(f.read())


def rsa_encrypt(data: bytes, public_key: RSA.RsaKey) -> bytes:
    """
    Chiffre 'data' avec la clé publique RSA.
    Utilise OAEP + SHA-256 (plus sûr que PKCS#1 v1.5).
    Usage : chiffrer la clé de session AES côté PDA.
    """
    cipher = PKCS1_OAEP.new(public_key, hashAlgo=SHA256)
    return cipher.encrypt(data)


def rsa_decrypt(encrypted_data: bytes, private_key: RSA.RsaKey) -> bytes:
    """
    Déchiffre 'encrypted_data' avec la clé privée RSA.
    Usage : récupérer la clé de session AES côté Back-Office.
    """
    cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)
    return cipher.decrypt(encrypted_data)


def init_keys() -> None:
    """
    Initialise les clés RSA au démarrage.
    Si elles n'existent pas, les génère et les sauvegarde.
    Appelé une seule fois au lancement du Back-Office.
    """
    if not os.path.exists(PRIVATE_KEY_PATH):
        print("[RSA] Aucune clé trouvée — génération en cours...")
        private_pem, public_pem = generate_rsa_keypair()
        save_keypair(private_pem, public_pem)
        print("[RSA] Clés RSA-2048 générées avec succès.")
    else:
        print("[RSA] Clés RSA existantes chargées.")