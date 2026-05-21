import hashlib
import hmac
import os
import binascii


def generate_salt() -> str:
    """
    Génère un sel aléatoire de 32 bytes (64 caractères hex).
    Chaque utilisateur a son propre sel → empêche les attaques par table arc-en-ciel.
    Appelé une seule fois à la création du compte.
    """
    return binascii.hexlify(os.urandom(32)).decode("utf-8")


def hash_password(password: str, salt: str) -> str:
    """
    Calcule SHA-256(password + salt).

    Pourquoi concaténer le sel au mot de passe ?
      - Même mot de passe + sel différent = hash totalement différent
      - Rend les attaques par dictionnaire et rainbow tables inutiles
      - SHA-256 produit une empreinte de 64 caractères hex (256 bits)

    Note : en production, on préférerait bcrypt ou Argon2 (plus lents donc
    plus résistants aux attaques par force brute). SHA-256 est utilisé ici
    car c'est la même bibliothèque que pour les hashs d'intégrité (cohérence).
    """
    combined = password + salt
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """
    Vérifie qu'un mot de passe correspond au hash stocké en base.
    Utilise hmac.compare_digest pour une comparaison à temps constant.
    """
    computed = hash_password(password, salt)
    return hmac.compare_digest(computed, stored_hash)