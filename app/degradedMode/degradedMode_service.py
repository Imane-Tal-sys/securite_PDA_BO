'degradeMode_service.py'
import asyncio
import httpx
import os
from datetime import datetime, timezone

from .local_db        import init_local_db
from .buffer_store    import push_transaction, get_pending_count
from .network_monitor import NetworkMonitor
from .sync_service    import SyncService
from .schemas         import SyncResult, NetworkStatus

BACKOFFICE_URL = os.getenv("BACKOFFICE_URL", "http://api:8000")
SEND_TIMEOUT_S = 8


class DegradedService:
    """
    Point d'entrée unique pour les opérations terrain.

    L'agent PDA appelle uniquement submit_operation() —
    ce service décide de façon transparente entre :
      - Envoi direct si le réseau est disponible
      - Mise en tampon SQLite si hors ligne

    Démarrage :
        service = DegradedService(jwt_token)
        await service.start()   # Lance le NetworkMonitor en arrière-plan
    """

    def __init__(self, jwt_token: str = ""):
        self._monitor     = NetworkMonitor()
        self._sync        = SyncService(jwt_token)
        self._initialized = False

        # Quand le réseau revient → synchronisation automatique
        self._monitor.on_online(self._on_network_restored)

    async def start(self) -> None:
        """
        Initialise la base SQLite et lance le NetworkMonitor.
        À appeler une seule fois au démarrage de l'app.
        """
        init_local_db()
        self._initialized = True

        # Vérification initiale
        await self._monitor.force_check()

        # Lancement du monitoring en arrière-plan
        asyncio.create_task(self._monitor.start())

        pending = get_pending_count()
        if pending > 0:
            print(f"[DegradedService] {pending} transaction(s) en attente "
                  "depuis la dernière session — synchronisation au prochain retour réseau")

        print(f"[DegradedService] Prêt — mode: "
              f"{'EN LIGNE' if self._monitor.is_online else 'HORS LIGNE'}")

    def update_token(self, token: str) -> None:
        """Met à jour le token JWT après chaque reconnexion."""
        self._sync.update_token(token)

    # ------------------------------------------------------------------
    # Interface principale
    # ------------------------------------------------------------------

    async def submit_operation(
        self,
        operation_type:   str,
        transaction_id:   str,
        encrypted_packet: dict,
        endpoint_path:    str,
        jwt_token:        str
    ) -> dict:
        """
        Soumet une opération terrain de façon résiliente.

        Si en ligne  → envoie directement et retourne la réponse du Back-Office.
        Si hors ligne → met en tampon SQLite et retourne une réponse locale.

        encrypted_packet : paquet déjà chiffré par CryptoService.
        endpoint_path    : '/operations/controle/chiffre' ou '/operations/vente/chiffre'
        """
        # Vérification en temps réel (force_check si dernière vérif > 15s)
        is_online = await self._monitor.force_check()

        if is_online:
            return await self._send_direct(
                operation_type, transaction_id,
                encrypted_packet, endpoint_path, jwt_token
            )
        else:
            return self._store_locally(
                operation_type, transaction_id, encrypted_packet
            )

    # ------------------------------------------------------------------
    # Envoi direct (mode en ligne)
    # ------------------------------------------------------------------

    async def _send_direct(
        self,
        operation_type:   str,
        transaction_id:   str,
        encrypted_packet: dict,
        endpoint_path:    str,
        jwt_token:        str
    ) -> dict:
        """
        Envoie directement au Back-Office.
        En cas d'échec réseau → bascule automatiquement en stockage local.
        """
        url     = f"{BACKOFFICE_URL}{endpoint_path}"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type":  "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_S) as client:
                response = await client.post(url, json=encrypted_packet, headers=headers)
                response.raise_for_status()
                return {
                    "mode":      "online",
                    "success":   True,
                    "response":  response.json(),
                    "buffered":  False
                }

        except (httpx.RequestError, httpx.HTTPStatusError, Exception) as e:
            # Echec réseau inattendu → fallback vers le tampon local
            print(f"[DegradedService] Envoi direct échoué ({e}) — "
                  "basculement vers tampon local")
            return self._store_locally(
                operation_type, transaction_id, encrypted_packet
            )

    # ------------------------------------------------------------------
    # Stockage local (mode hors ligne)
    # ------------------------------------------------------------------

    def _store_locally(
        self,
        operation_type:   str,
        transaction_id:   str,
        encrypted_packet: dict
    ) -> dict:
        """
        Stocke le paquet chiffré dans SQLite.
        Retourne une réponse locale confirmant la mise en tampon.
        """
        local_id = push_transaction(
            transaction_id   = transaction_id,
            operation_type   = operation_type,
            encrypted_packet = encrypted_packet
        )
        pending = get_pending_count()

        return {
            "mode":      "offline",
            "success":   True,
            "local_id":  local_id,
            "buffered":  True,
            "pending":   pending,
            "message":   (
                f"Transaction mise en tampon (local_id={local_id}). "
                f"{pending} transaction(s) en attente de synchronisation."
            )
        }

    # ------------------------------------------------------------------
    # Callback réseau rétabli
    # ------------------------------------------------------------------

    async def _on_network_restored(self) -> None:
        """
        Déclenché automatiquement par NetworkMonitor quand le réseau revient.
        Lance la synchronisation de toutes les transactions en attente.
        """
        pending = get_pending_count()
        if pending == 0:
            print("[DegradedService] Réseau rétabli — aucune transaction en attente")
            return

        print(f"[DegradedService] Réseau rétabli — "
              f"synchronisation de {pending} transaction(s)")
        result = await self._sync.sync_pending()

        print(f"[DegradedService] Synchronisation terminée — "
              f"OK: {result.sent_ok}, ECHEC: {result.sent_failed}")

    # ------------------------------------------------------------------
    # Synchronisation manuelle
    # ------------------------------------------------------------------

    async def force_sync(self) -> SyncResult:
        """
        Déclenche une synchronisation manuelle.
        Utile pour le bouton "Synchroniser maintenant" de l'interface PDA.
        """
        if not self._monitor.is_online:
            return SyncResult(
                total_pending = get_pending_count(),
                sent_ok       = 0,
                sent_failed   = 0,
                errors        = ["Impossible de synchroniser : réseau non disponible"]
            )
        return await self._sync.sync_pending()

    @property
    def network_status(self) -> dict:
        return self._monitor.status

    @property
    def pending_count(self) -> int:
        return get_pending_count()