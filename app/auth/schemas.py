'schemas.py'
from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    """Données envoyées par le PDA lors de la connexion."""
    matricule: str
    password:  str
    device_id: str     # Identifiant matériel unique du terminal PDA


class LoginResponse(BaseModel):
    """Réponse renvoyée au PDA après authentification réussie."""
    access_token:    str
    session_key:     str    # Clé AES éphémère base64 pour cette session
    expires_at:      str
    token_type:      str
    is_first_login:  bool   # True → le PDA doit afficher l'écran de changement de mdp


class ChangePasswordRequest(BaseModel):
    """Changement de mot de passe (obligatoire à la première connexion)."""
    matricule:    str
    old_password: str
    new_password: str
    device_id:    str


class RegisterDeviceRequest(BaseModel):
    """Enregistrement d'un nouveau terminal (admin sécurité uniquement)."""
    matricule:  str
    device_id:  str


class AgentInfo(BaseModel):
    """Informations minimales de l'agent utilisées dans les autres modules."""
    matricule:  str
    nom:        str
    prenom:     str
    role_id:    int
    device_id:  str