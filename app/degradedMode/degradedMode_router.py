from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_agent
from app.auth.schemas import AgentInfo
from app.crypto.crypto_service import CryptoService
from app.crypto.schemas import EncryptedPayload
from app.db.database import get_db

from .degradedMode_service import DegradedService
from .buffer_store import get_db_stats, get_failed_transactions
from .schemas import SyncResult

router = APIRouter(prefix="/degraded", tags=["Mode dégradé"])
crypto = CryptoService()

# Instance globale partagée (initialisée dans main.py)
degraded_svc: DegradedService = None


def get_degraded_service() -> DegradedService:
    """Dépendance FastAPI retournant l'instance partagée."""
    global degraded_svc
    if degraded_svc is None:
        raise HTTPException(503, "Service mode dégradé non initialisé")
    return degraded_svc


@router.post("/submit/controle")
async def submit_controle_degrade(
    packet: EncryptedPayload,
    agent: AgentInfo = Depends(get_current_agent),
    svc: DegradedService = Depends(get_degraded_service)
):
    """Soumet un contrôle chiffré avec gestion automatique du mode hors-ligne."""
    return await svc.submit_operation(
        operation_type="controle",
        transaction_id=packet.transaction_id,
        encrypted_packet=packet.model_dump(),
        endpoint_path="/operations/controle/chiffre",
        jwt_token=agent.matricule   # Le vrai token JWT serait dans le header
    )


@router.post("/submit/vente")
async def submit_vente_degrade(
    packet: EncryptedPayload,
    agent: AgentInfo = Depends(get_current_agent),
    svc: DegradedService = Depends(get_degraded_service)
):
    """Soumet une vente chiffrée avec gestion automatique du mode hors-ligne."""
    return await svc.submit_operation(
        operation_type="vente",
        transaction_id=packet.transaction_id,
        encrypted_packet=packet.model_dump(),
        endpoint_path="/operations/vente/chiffre",
        jwt_token=agent.matricule
    )


@router.post("/sync", response_model=SyncResult)
async def force_sync(
    agent: AgentInfo = Depends(get_current_agent),
    svc: DegradedService = Depends(get_degraded_service)
):
    """Déclenche une synchronisation manuelle des transactions en attente."""
    return await svc.force_sync()


@router.get("/status")
async def get_status(
    agent: AgentInfo = Depends(get_current_agent),
    svc: DegradedService = Depends(get_degraded_service)
):
    """Retourne l'état du réseau et les statistiques du tampon local."""
    return {
        "network": svc.network_status,
        "buffer": get_db_stats(),
        "pending": svc.pending_count
    }


@router.get("/failed")
async def get_failed(
    agent: AgentInfo = Depends(get_current_agent),
    svc: DegradedService = Depends(get_degraded_service)
):
    """Retourne les transactions qui ont dépassé le nombre max de tentatives."""
    return get_failed_transactions()