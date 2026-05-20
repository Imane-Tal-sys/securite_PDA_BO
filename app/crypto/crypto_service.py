'crypto_service.py'
import json
import base64
import uuid
import logging
from typing import Dict, Any

from .rsa import (
    load_public_key, load_private_key,
    rsa_encrypt, rsa_decrypt, init_keys
)
from .aes import generate_aes_key, aes_encrypt, aes_decrypt
from .schemas import EncryptedPayload

logger = logging.getLogger(__name__)

class CryptoService:
    _keys_initialized = False

    def __init__(self):
        if not CryptoService._keys_initialized:
            init_keys()
            CryptoService._keys_initialized = True

    def encrypt_payload(self, payload: Dict[str, Any], device_id: str) -> EncryptedPayload:
        aes_key = generate_aes_key()
        public_key = load_public_key()
        encrypted_key = rsa_encrypt(aes_key, public_key)
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted = aes_encrypt(payload_bytes, aes_key)

        return EncryptedPayload(
            encrypted_key=base64.b64encode(encrypted_key).decode("ascii"),
            iv=base64.b64encode(encrypted["iv"]).decode("ascii"),
            tag=base64.b64encode(encrypted["tag"]).decode("ascii"),
            ciphertext=base64.b64encode(encrypted["data"]).decode("ascii"),
            device_id=device_id,
            transaction_id=str(uuid.uuid4())
        )

    def decrypt_payload(self, packet: EncryptedPayload) -> Dict[str, Any]:
        private_key = load_private_key()
        try:
            enc_key_bytes = base64.b64decode(packet.encrypted_key)
            iv_bytes = base64.b64decode(packet.iv)
            tag_bytes = base64.b64decode(packet.tag)
            cipher_bytes = base64.b64decode(packet.ciphertext)

            aes_key = rsa_decrypt(enc_key_bytes, private_key)
            encrypted = {"iv": iv_bytes, "tag": tag_bytes, "data": cipher_bytes}
            plaintext = aes_decrypt(encrypted, aes_key)
            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"Échec du déchiffrement : {e}", exc_info=True)
            raise ValueError(f"Échec du déchiffrement ou du parsing : {e}")