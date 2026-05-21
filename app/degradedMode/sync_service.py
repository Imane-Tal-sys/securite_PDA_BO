'modeDegrade_service.py'
import asyncio
import httpx
import os
from datetime import datetime, timezone

from .buffer_store import (
    get_pending_transactions,
    mark_synchronized,
    increment_retry,
    get_pending_count
)
from .schemas import SyncResult

BACKOFFICE_URL  = os.getenv("BACKOFFICE_URL", "http://api:8000")
SYNC_BATCH_SIZE = 20    # Nombre de transactions par batch de sync
SEND_TIMEOUT_S  = 10    # Timeout par requête d'envoi

# Endpoints de destination par type d'opération
ENDPOINTS = {
    "controle": f"{BACKOFFICE_URL}/operations/controle/chiffre",
    "vente":    f"{BACKOFFICE_URL}/operations/vente/chiffre",
}


class SyncService:
    """
    Service de synchronisation des transactions hors-ligne.

    Fonctionnement :
      1. Lit le tampon SQLite par batches de SYNC_BATCH_SIZE (FIFO)
      2. Pour chaque transaction, envoie le paquet chiffré au Back-Office
      3. Si succès → marque synchronized=1
      4. Si échec → incrémente retry_count, réessaiera au prochain cycle
      5. Log un résumé de chaque cycle de synchronisation
    """

    def __init__(self, jwt_token: str = ""):
        """
        jwt_token : token JWT de la session courante.
        Nécessaire car le Back-Office exige l'authentification même
        pour les transactions différées.
        """
        self._token    = jwt_token
        self._syncing  = False   # Verrou pour éviter les synchronisations parallèles

    def update_token(self, new_token: str) -> None:
        """Met à jour le token JWT (appelé après chaque login)."""
        self._token = new_token

    async def sync_pending(self) -> SyncResult:
        """
        Synchronise toutes les transactions en attente.
        Retourne un SyncResult avec le bilan de l'opération.

        Le verrou _syncing empêche deux synchronisations simultanées
        (ex: retour réseau + sync manuelle déclenchée en même temps).
        """
        if self._syncing:
            print("[Sync] Synchronisation déjà en cours — ignoré")
            return SyncResult(
                total_pending=0, sent_ok=0, sent_failed=0,
                errors=["Synchronisation déjà en cours"]
            )

        self._syncing   = True
        pending_count   = get_pending_count()
        sent_ok         = 0
        sent_failed     = 0
        errors          = []

        print(f"[Sync] Démarrage — {pending_count} transaction(s) en attente")

        try:
            # Traitement par batches pour ne pas saturer la mémoire
            while True:
                batch = get_pending_transactions(limit=SYNC_BATCH_SIZE)
                if not batch:
                    break   # Plus rien en attente → terminé

                for txn in batch:
                    success, error = await self._send_transaction(txn)
                    if success:
                        mark_synchronized(txn["local_id"])
                        sent_ok += 1
                        print(f"[Sync] OK: {txn['transaction_id'][:8]}... "
                              f"(retry={txn['retry_count']})")
                    else:
                        increment_retry(txn["local_id"], error)
                        sent_failed += 1
                        errors.append(
                            f"Transaction {txn['transaction_id'][:8]}...: {error}"
                        )
                        print(f"[Sync] ECHEC: {txn['transaction_id'][:8]}... "
                              f"— {error}")

                    # Petite pause entre envois pour ne pas saturer le Back-Office
                    await asyncio.sleep(0.1)

        finally:
            self._syncing = False

        result = SyncResult(
            total_pending = pending_count,
            sent_ok       = sent_ok,
            sent_failed   = sent_failed,
            errors        = errors
        )
        print(f"[Sync] Terminé — OK: {sent_ok}, ECHEC: {sent_failed}")
        return result

    async def _send_transaction(self, txn: dict) -> tuple[bool, str]:
        """
        Envoie un paquet chiffré au Back-Office.

        Retourne (True, "") si succès.
        Retourne (False, message_erreur) si échec.

        Le paquet est envoyé tel quel (déjà chiffré par CryptoService) —
        SyncService ne voit jamais les données en clair.
        """
        operation_type = txn["operation_type"]
        endpoint       = ENDPOINTS.get(operation_type)

        if not endpoint:
            return False, f"Type d'opération inconnu : {operation_type}"

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_S) as client:
                response = await client.post(
                    endpoint,
                    json    = txn["encrypted_packet"],
                    headers = headers
                )

                if response.status_code == 200:
                    return True, ""

                # HTTP 409 = transaction déjà reçue (doublon réseau normal)
                # On la marque quand même comme synchronized
                if response.status_code == 409:
                    return True, ""

                return False, f"HTTP {response.status_code}: {response.text[:200]}"

        except httpx.TimeoutException:
            return False, "Timeout — Back-Office non joignable"
        except httpx.RequestError as e:
            return False, f"Erreur réseau : {str(e)[:200]}"
        except Exception as e:
            return False, f"Erreur inattendue : {str(e)[:200]}"