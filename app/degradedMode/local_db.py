import sqlite3
import os
from datetime import datetime

def get_connection() -> sqlite3.Connection:
    """
    Retourne une connexion SQLite avec WAL mode activé.
    Lit le chemin SQLite à chaque appel via la variable d'environnement SQLITE_PATH.
    Permet aux tests de changer dynamiquement le chemin (fichier temporaire ou :memory:).
    """
    sqlite_path = os.getenv("SQLITE_PATH", "data/pda_buffer.db")

    # Ne pas créer de répertoire pour la base mémoire
    if sqlite_path != ":memory:":
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)

    conn = sqlite3.connect(
        sqlite_path,
        check_same_thread=False,
        timeout=10
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_local_db() -> None:
    """
    Crée les tables SQLite si elles n'existent pas.
    Appelé une seule fois au démarrage de l'application PDA.
    """
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transaction_buffer (
            local_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id   TEXT    NOT NULL UNIQUE,
            operation_type   TEXT    NOT NULL,
            encrypted_packet TEXT    NOT NULL,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            retry_count      INTEGER NOT NULL DEFAULT 0,
            synchronized     INTEGER NOT NULL DEFAULT 0,
            synced_at        TEXT    NULL,
            last_error       TEXT    NULL
        );

        CREATE INDEX IF NOT EXISTS idx_buffer_sync
            ON transaction_buffer (synchronized, created_at ASC);

        CREATE TABLE IF NOT EXISTS sync_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_started_at  TEXT    NOT NULL,
            sync_ended_at    TEXT    NULL,
            total_pending    INTEGER NOT NULL DEFAULT 0,
            sent_ok          INTEGER NOT NULL DEFAULT 0,
            sent_failed      INTEGER NOT NULL DEFAULT 0,
            notes            TEXT    NULL
        );
    """)
    conn.commit()
    conn.close()
    print(f"[SQLite] Base locale initialisée : {os.getenv('SQLITE_PATH', 'data/pda_buffer.db')}")

def get_db_stats() -> dict:
    """Retourne des statistiques sur le tampon local."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*)                              AS total,
            SUM(CASE WHEN synchronized=0 THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN synchronized=1 THEN 1 ELSE 0 END) AS synced
        FROM transaction_buffer
    """).fetchone()
    conn.close()
    return dict(row)