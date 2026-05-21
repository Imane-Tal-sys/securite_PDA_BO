'session.py'
import os
import jwt
import base64
from datetime import datetime, timedelta, timezone
from app.crypto.aes import generate_aes_key

# Clé secrète pour signer les JWT (stockée dans .env)
JWT_SECRET    = os.getenv("SECRET_KEY", "dev_secret_change_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 480   # 8 heures (durée d'un shift agent)


def create_session(matricule: str, role_id: int, device_id: str) -> dict:
    """
    Crée une session sécurisée après authentification réussie.

    Retourne :
      - access_token : JWT signé contenant l'identité de l'agent
      - session_key  : clé AES-256 éphémère encodée base64
                       (utilisée par le module Crypto pour cette session)
      - expires_at   : heure d'expiration UTC

    La clé AES éphémère est générée ici → une nouvelle clé par connexion.
    Elle n'est jamais stockée en base, seulement en mémoire côté PDA.
    """
    expiration = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)

    # Payload JWT : informations minimales (pas de données sensibles dans le JWT)
    payload = {
        "sub":       matricule,           # Subject (identifiant unique)
        "role_id":   role_id,
        "device_id": device_id,
        "exp":       expiration,
        "iat":       datetime.now(timezone.utc)  # Issued At
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Clé AES éphémère unique pour cette session
    session_aes_key = generate_aes_key()

    return {
        "access_token": token,
        "session_key":  base64.b64encode(session_aes_key).decode(),
        "expires_at":   expiration.isoformat(),
        "token_type":   "Bearer"
    }


def verify_token(token: str) -> dict:
    """
    Vérifie la signature et l'expiration du JWT.
    Retourne le payload si valide, lève une exception sinon.

    jwt.decode vérifie automatiquement :
      - La signature HMAC-SHA256 avec JWT_SECRET
      - La date d'expiration (champ 'exp')
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])