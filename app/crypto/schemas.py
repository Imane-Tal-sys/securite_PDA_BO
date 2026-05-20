'schemas.py'
from pydantic import BaseModel
import base64


class EncryptedPayload(BaseModel):
    """
    Structure du paquet chiffré envoyé par le PDA au Back-Office.

    Tous les champs bytes sont encodés en base64 pour le transport JSON.

    - encrypted_key : clé AES chiffrée avec RSA (seul le Back-Office peut la déchiffrer)
    - iv            : vecteur d'initialisation AES-GCM (16 bytes)
    - tag           : tag d'authentification GCM (16 bytes)
    - ciphertext    : données métier chiffrées (contrôle ou vente)
    - device_id     : identifiant du terminal PDA (Device Binding)
    - transaction_id: UUID unique anti-rejeu
    """
    encrypted_key:  str   # base64(RSA_pub(aes_key))
    iv:             str   # base64(iv)
    tag:            str   # base64(tag_gcm)
    ciphertext:     str   # base64(AES_GCM(payload_json))
    device_id:      str
    transaction_id: str


class DecryptedResponse(BaseModel):
    """Réponse du Back-Office après vérification et déchiffrement."""
    success:        bool
    transaction_id: str
    message:        str