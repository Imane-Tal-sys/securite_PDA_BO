'app/integrite/hash.py'
import hashlib
import hmac
import json
import os


def compute_data_hash(payload: dict) -> str:
    """
    Calcule le hash SHA-256 du payload JSON d'une transaction.

    Ce hash scelle le contenu de la transaction :
    si un seul champ est modifié en base, le hash recalculé
    ne correspondra plus → falsification détectée.

    Le payload est sérialisé avec tri des clés (sort_keys=True)
    pour garantir un résultat identique quelle que soit
    l'ordre d'insertion des champs.
    """
    payload_bytes = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(',', ':')   # Sans espaces → déterministe
    ).encode('utf-8')

    return hashlib.sha256(payload_bytes).hexdigest()


def compute_chain_hash(
    payload: dict,
    previous_hash: str,
    salt: str
) -> str:
    """
    Calcule le hash de chaîne : SHA-256(payload + hash_précédent + sel).

    C'est ce hash qui crée le lien entre les maillons :
      - 'payload'       : les données de la transaction
      - 'previous_hash' : hash_chain du maillon N-1 → crée la dépendance
      - 'salt'          : sel aléatoire unique → empêche les attaques
                          par pré-calcul (rainbow tables)

    Si previous_hash change (parce qu'un maillon antérieur a été modifié),
    ce hash change aussi → cascade de ruptures détectable.
    """
    data_str = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(',', ':')
    )
    # Concaténation des trois composants
    combined = f"{data_str}|{previous_hash}|{salt}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def generate_chain_salt() -> str:
    """
    Génère un sel aléatoire de 32 bytes (64 caractères hex) pour un maillon.
    Chaque maillon a son propre sel → unicité garantie.
    """
    return os.urandom(32).hex()


def verify_data_hash(payload: dict, stored_hash: str) -> bool:
    """
    Vérifie que le hash d'un payload correspond au hash stocké.
    Utilise hmac.compare_digest pour éviter les attaques temporelles.
    """
    computed = compute_data_hash(payload)
    return hmac.compare_digest(computed, stored_hash)


def verify_chain_hash(
    payload: dict,
    previous_hash: str,
    salt: str,
    stored_chain_hash: str
) -> bool:
    """
    Vérifie le hash de chaîne d'un maillon.
    Retourne False si le maillon a été altéré ou si la chaîne est rompue.
    """
    computed = compute_chain_hash(payload, previous_hash, salt)
    return hmac.compare_digest(computed, stored_chain_hash)