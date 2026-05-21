'dependencies.py'
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .session import verify_token
from .schemas import AgentInfo
import jwt

bearer_scheme = HTTPBearer()


def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> AgentInfo:
    """
    Dépendance FastAPI injectée dans toutes les routes protégées.

    Extrait et valide le JWT du header Authorization: Bearer <token>.
    Retourne les infos de l'agent si le token est valide.

    Usage dans une route :
        @app.post("/operation/controle")
        def creer_controle(agent: AgentInfo = Depends(get_current_agent)):
            ...
    """
    try:
        payload = verify_token(credentials.credentials)
        return AgentInfo(
            matricule  = payload["sub"],
            nom        = "",       # Non stocké dans le JWT (requête DB si besoin)
            prenom     = "",
            role_id    = payload.get("role_id", 0),
            device_id  = payload["device_id"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide.",
            headers={"WWW-Authenticate": "Bearer"}
        )