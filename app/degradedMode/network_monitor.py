'network_monitor.py'
import asyncio
import httpx
import os
from datetime import datetime, timezone
from typing   import Callable, Optional

BACKOFFICE_URL     = os.getenv("BACKOFFICE_URL", "http://api:8000")
HEALTH_ENDPOINT    = f"{BACKOFFICE_URL}/health"
CHECK_INTERVAL_S   = 15    # Vérification toutes les 15 secondes
TIMEOUT_S          = 5     # Timeout de la requête de test
MAX_FAILURES       = 3     # Nombre d'échecs consécutifs avant de déclarer hors-ligne


class NetworkMonitor:
    """
    Moniteur de connectivité réseau asynchrone.

    Tourne en arrière-plan et appelle des callbacks quand
    le statut réseau change (online → offline ou offline → online).

    Usage :
        monitor = NetworkMonitor()
        monitor.on_online(callback_sync)
        asyncio.create_task(monitor.start())
    """

    def __init__(self):
        self._online:              bool          = True
        self._consecutive_failures: int          = 0
        self._last_check:          datetime      = datetime.now(timezone.utc)
        self._latency_ms:          Optional[float] = None
        self._on_online_callbacks: list[Callable]  = []
        self._on_offline_callbacks: list[Callable] = []

    # ------------------------------------------------------------------
    # Enregistrement des callbacks
    # ------------------------------------------------------------------

    def on_online(self, callback: Callable) -> None:
        """Enregistre une fonction appelée quand le réseau revient."""
        self._on_online_callbacks.append(callback)

    def on_offline(self, callback: Callable) -> None:
        """Enregistre une fonction appelée quand le réseau est perdu."""
        self._on_offline_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Propriétés d'état
    # ------------------------------------------------------------------

    @property
    def is_online(self) -> bool:
        return self._online

    @property
    def status(self) -> dict:
        return {
            "online":               self._online,
            "latency_ms":           self._latency_ms,
            "last_check":           self._last_check.isoformat(),
            "consecutive_failures": self._consecutive_failures,
        }

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Boucle infinie de vérification de connectivité.
        À lancer avec asyncio.create_task() au démarrage de l'app.
        """
        print(f"[NetworkMonitor] Démarré — vérification toutes les {CHECK_INTERVAL_S}s")
        while True:
            await self._check_connectivity()
            await asyncio.sleep(CHECK_INTERVAL_S)

    async def _check_connectivity(self) -> None:
        """
        Effectue un GET /health vers le Back-Office.
        Met à jour l'état et déclenche les callbacks si le statut change.
        """
        was_online = self._online
        t_start    = asyncio.get_event_loop().time()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                response = await client.get(HEALTH_ENDPOINT)
                response.raise_for_status()

            latency = (asyncio.get_event_loop().time() - t_start) * 1000
            self._latency_ms           = round(latency, 1)
            self._consecutive_failures = 0
            self._online               = True

        except (httpx.RequestError, httpx.HTTPStatusError, Exception):
            self._consecutive_failures += 1
            self._latency_ms            = None

            # On ne déclare hors-ligne qu'après MAX_FAILURES échecs consécutifs
            # pour éviter les faux positifs sur des pics de latence
            if self._consecutive_failures >= MAX_FAILURES:
                self._online = False

        self._last_check = datetime.now(timezone.utc)

        # Déclenchement des callbacks si le statut a changé
        if was_online and not self._online:
            print(f"[NetworkMonitor] Réseau PERDU après "
                  f"{self._consecutive_failures} échecs consécutifs")
            for cb in self._on_offline_callbacks:
                try:
                    await cb() if asyncio.iscoroutinefunction(cb) else cb()
                except Exception as e:
                    print(f"[NetworkMonitor] Erreur callback offline: {e}")

        elif not was_online and self._online:
            print(f"[NetworkMonitor] Réseau RÉTABLI — "
                  f"latence: {self._latency_ms}ms")
            for cb in self._on_online_callbacks:
                try:
                    await cb() if asyncio.iscoroutinefunction(cb) else cb()
                except Exception as e:
                    print(f"[NetworkMonitor] Erreur callback online: {e}")

    async def force_check(self) -> bool:
        """Vérifie immédiatement la connectivité (utilisé avant un envoi)."""
        await self._check_connectivity()
        return self._online