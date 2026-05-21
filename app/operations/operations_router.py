'operations_router.py'
from fastapi        import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies        import get_current_agent
from app.auth.schemas             import AgentInfo
from app.crypto.crypto_service    import CryptoService
from app.crypto.schemas           import EncryptedPayload
from app.db.database              import get_db

from .controle_service import ControleService
from .vente_service    import VenteService
from .payload_builder  import build_controle_payload, build_vente_payload
from .schemas          import (
    ControleRequest, ControleResponse,
    VenteRequest,    VenteResponse,
    OperationPayload
)

router          = APIRouter(prefix="/operations", tags=["Opérations terrain"])
crypto_service  = CryptoService()
controle_svc    = ControleService()
vente_svc       = VenteService()


# -----------------------------------------------------------------------
# Endpoint contrôle — deux modes :
#   a) Payload clair (tests internes / réseau sécurisé)
#   b) Payload chiffré (production PDA → Back-Office)
# -----------------------------------------------------------------------

@router.post("/controle", response_model=ControleResponse)
def soumettre_controle(
    request: ControleRequest,
    agent:   AgentInfo = Depends(get_current_agent),
    db:      Session   = Depends(get_db)
):
    """
    Endpoint mode clair — pour les tests et le réseau interne.
    En production, utiliser /controle/chiffre.
    """
    payload_obj = build_controle_payload(request, agent.matricule, agent.device_id)
    return controle_svc.process_controle(payload_obj, db)


@router.post("/controle/chiffre", response_model=ControleResponse)
def soumettre_controle_chiffre(
    packet: EncryptedPayload,
    agent:  AgentInfo = Depends(get_current_agent),
    db:     Session   = Depends(get_db)
):
    """
    Endpoint production — payload AES-GCM chiffré par le PDA.

    Pipeline complet :
      1. Vérification JWT (Depends get_current_agent)
      2. Déchiffrement AES-GCM + vérification tag
      3. Validation anti-rejeu + métier
      4. INSERT + scellement HashChain
    """
    # Vérification que le device_id du token correspond au paquet
    if packet.device_id != agent.device_id:
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "device_id du paquet ne correspond pas au token JWT"
        )

    try:
        raw_payload = crypto_service.decrypt_payload(packet)
    except ValueError:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "Falsification détectée : tag AES-GCM invalide"
        )

    payload_obj = OperationPayload(**raw_payload)
    return controle_svc.process_controle(payload_obj, db)


# -----------------------------------------------------------------------
# Endpoint vente
# -----------------------------------------------------------------------

@router.post("/vente", response_model=VenteResponse)
def soumettre_vente(
    request: VenteRequest,
    agent:   AgentInfo = Depends(get_current_agent),
    db:      Session   = Depends(get_db)
):
    """Endpoint mode clair — tests et réseau interne."""
    payload_obj = build_vente_payload(request, agent.matricule, agent.device_id)
    return vente_svc.process_vente(payload_obj, db)


@router.post("/vente/chiffre", response_model=VenteResponse)
def soumettre_vente_chiffre(
    packet: EncryptedPayload,
    agent:  AgentInfo = Depends(get_current_agent),
    db:     Session   = Depends(get_db)
):
    """Endpoint production — payload AES-GCM chiffré par le PDA."""
    if packet.device_id != agent.device_id:
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "device_id du paquet ne correspond pas au token JWT"
        )

    try:
        raw_payload = crypto_service.decrypt_payload(packet)
    except ValueError:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "Falsification détectée : tag AES-GCM invalide"
        )

    payload_obj = OperationPayload(**raw_payload)
    return vente_svc.process_vente(payload_obj, db)


# -----------------------------------------------------------------------
# Endpoints de consultation (Back-Office / supervision)
# -----------------------------------------------------------------------

@router.get("/controles/mission/{mission_id}")
def get_controles_par_mission(
    mission_id: int,
    agent:      AgentInfo = Depends(get_current_agent),
    db:         Session   = Depends(get_db)
):
    """Retourne tous les contrôles d'une mission donnée."""
    rows = db.execute(
        text("""
            SELECT c.*, h.[ChainHash], h.[Sequence] AS ChainSequence
            FROM [OPERATION].[Controle] c
            LEFT JOIN [OPERATION].[HashChain] h
                ON h.[SourceId] = c.[ControleId]
               AND h.[TransactionType] = 'controle'
            WHERE c.[MissionId] = :mission_id
            ORDER BY c.[DateHeureControle] DESC
        """),
        {"mission_id": mission_id}
    ).fetchall()

    return [dict(r._mapping) for r in rows]


@router.get("/ventes/mission/{mission_id}")
def get_ventes_par_mission(
    mission_id: int,
    agent:      AgentInfo = Depends(get_current_agent),
    db:         Session   = Depends(get_db)
):
    """Retourne toutes les ventes d'une mission donnée."""
    rows = db.execute(
        text("""
            SELECT v.*, h.[ChainHash], h.[Sequence] AS ChainSequence
            FROM [OPERATION].[VenteBillet] v
            LEFT JOIN [OPERATION].[HashChain] h
                ON h.[SourceId] = v.[Id]
               AND h.[TransactionType] = 'vente'
            WHERE v.[MissionId] = :mission_id
            ORDER BY v.[DateOperation] DESC
        """),
        {"mission_id": mission_id}
    ).fetchall()

    return [dict(r._mapping) for r in rows]