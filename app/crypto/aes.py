'aes.py'
import os
from Crypto.Cipher import AES

AES_KEY_SIZE = 32   # 256 bits
IV_SIZE      = 16   # 128 bits (nonce GCM)
TAG_SIZE     = 16   # 128 bits (tag d'authentification GCM)

def generate_aes_key() -> bytes:
    return os.urandom(AES_KEY_SIZE)

def aes_encrypt(plaintext: bytes, key: bytes) -> dict:
    iv = os.urandom(IV_SIZE)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return {"iv": iv, "tag": tag, "data": ciphertext}

def aes_decrypt(encrypted: dict, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_GCM, nonce=encrypted["iv"])
    return cipher.decrypt_and_verify(encrypted["data"], encrypted["tag"])