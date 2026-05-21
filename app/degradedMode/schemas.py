'schemas.py'
from pydantic import BaseModel
from typing   import Optional
from datetime import datetime


class BufferedTransaction(BaseModel):
    """
    Représentation d'une transaction en attente dans le tampon SQLite.
    """
    local_id:         int
    transaction_id:   str          # UUID unique (anti-rejeu)
    operation_type:   str          # 'controle' ou 'vente'
    encrypted_packet: str          # Paquet AES-GCM chiffré (base64 JSON)
    created_at:       datetime
    retry_count:      int          # Nombre de tentatives d'envoi
    synchronized:     bool         # False = en attente, True = envoyé


class SyncResult(BaseModel):
    """Résultat d'une opération de synchronisation."""
    total_pending:   int
    sent_ok:         int
    sent_failed:     int
    errors:          list[str]


class NetworkStatus(BaseModel):
    """État de la connectivité réseau."""
    online:          bool
    latency_ms:      Optional[float] = None
    last_check:      datetime
    consecutive_failures: int