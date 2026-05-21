'buffer_store.py'
import json
import sqlite3
from datetime import datetime, timezone
from typing   import Optional

from .local_db import get_connection

MAX_RETRY = 5   # Nombre maximal de tentatives avant abandon


def push_transaction(
    transaction_id:   str,
    operation_type:   str,
    encrypted_packet: dict   # Déjà chiffré par le module Crypto (Phase 2)
) -> int:
    """
    Enregistre un paquet chiffré dans le tampon SQLite local.

    Le paquet est sérialisé en JSON string pour le stockage.
    Il a déjà été chiffré par CryptoService.encrypt_payload()
    avant d'arriver ici → SQLite ne stocke que du ciphertext.

    Retourne le local_id de l'enregistrement créé.
    """
    conn   = get_connection()
    packet_json = json.dumps(encrypted_packet)

    cursor = conn.execute(
        """
        INSERT INTO transaction_buffer
            (transaction_id, operation_type, encrypted_packet, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            transaction_id,
            operation_type,
            packet_json,
            datetime.now(timezone.utc).isoformat()
        )
    )
    local_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"[Buffer] Transaction {transaction_id[:8]}... mise en tampon "
          f"(local_id={local_id}, type={operation_type})")
    return local_id


def get_pending_transactions(limit: int = 50) -> list[dict]:
    """
    Récupère les transactions en attente dans l'ordre FIFO
    (created_at ASC = les plus anciennes d'abord).

    N'inclut que les transactions avec retry_count < MAX_RETRY
    pour éviter de boucler indéfiniment sur des transactions
    systématiquement rejetées par le Back-Office.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT local_id, transaction_id, operation_type,
               encrypted_packet, created_at, retry_count
        FROM transaction_buffer
        WHERE synchronized = 0
          AND retry_count  < ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (MAX_RETRY, limit)
    ).fetchall()
    conn.close()

    return [
        {
            "local_id":         row["local_id"],
            "transaction_id":   row["transaction_id"],
            "operation_type":   row["operation_type"],
            "encrypted_packet": json.loads(row["encrypted_packet"]),
            "created_at":       row["created_at"],
            "retry_count":      row["retry_count"],
        }
        for row in rows
    ]


def mark_synchronized(local_id: int) -> None:
    """
    Marque une transaction comme synchronisée avec succès.
    Elle restera en base pour l'audit mais ne sera plus renvoyée.
    """
    conn = get_connection()
    conn.execute(
        """
        UPDATE transaction_buffer
        SET synchronized = 1,
            synced_at    = ?
        WHERE local_id = ?
        """,
        (datetime.now(timezone.utc).isoformat(), local_id)
    )
    conn.commit()
    conn.close()


def increment_retry(local_id: int, error_msg: str) -> None:
    """
    Incrémente le compteur de tentatives après un échec d'envoi.
    Si retry_count atteint MAX_RETRY, la transaction est abandonnée
    (exclue des prochaines lectures par get_pending_transactions).
    """
    conn = get_connection()
    conn.execute(
        """
        UPDATE transaction_buffer
        SET retry_count = retry_count + 1,
            last_error  = ?
        WHERE local_id = ?
        """,
        (error_msg[:500], local_id)   # Tronquer à 500 chars
    )
    conn.commit()
    conn.close()


def get_pending_count() -> int:
    """Retourne le nombre de transactions en attente de synchronisation (retry_count < MAX_RETRY)."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM transaction_buffer WHERE synchronized = 0 AND retry_count < ?",
        (MAX_RETRY,)
    ).fetchone()[0]
    conn.close()
    return count


def get_failed_transactions() -> list[dict]:
    """
    Retourne les transactions qui ont dépassé MAX_RETRY.
    Ces transactions nécessitent une intervention manuelle.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT local_id, transaction_id, operation_type,
               created_at, retry_count, last_error
        FROM transaction_buffer
        WHERE synchronized = 0
          AND retry_count  >= ?
        ORDER BY created_at ASC
        """,
        (MAX_RETRY,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]