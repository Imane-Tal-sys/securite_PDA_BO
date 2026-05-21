'app/integrite/hashchain.py'
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from .hash import (
    compute_data_hash,
    compute_chain_hash,
    generate_chain_salt,
    verify_chain_hash
)

GENESIS_HASH = "0" * 64   # Hash fictif du bloc genesis (maillon 0)


def get_last_chain_hash(db: Session) -> tuple[str, int]:
    """
    Récupère le hash et la séquence du dernier maillon de la chaîne.

    Retourne (GENESIS_HASH, 0) si la chaîne est vide
    (première transaction de la journée).

    Utilise une requête verrouillante (UPDLOCK) pour éviter
    les conditions de concurrence lors d'insertions parallèles.
    """
    row = db.execute(
        text("""
            SELECT TOP 1 [ChainHash], [Sequence]
            FROM [OPERATION].[HashChain] WITH (UPDLOCK)
            ORDER BY [Sequence] DESC
        """)
    ).fetchone()

    if not row:
        return GENESIS_HASH, 0

    return row.ChainHash, row.Sequence


def add_to_chain(
    db:               Session,
    transaction_id:   str,
    transaction_type: str,   # 'controle' ou 'vente'
    source_id:        int,   # ControleId ou VenteBilletId
    payload:          dict,
    matricule:        str,
    device_id:        str
) -> dict:
    """
    Ajoute un nouveau maillon à la HashChain.

    Étapes :
      1. Récupère le hash du dernier maillon (verrouillage anti-concurrence)
      2. Génère un sel aléatoire unique pour ce maillon
      3. Calcule data_hash  = SHA-256(payload)
      4. Calcule chain_hash = SHA-256(payload + prev_hash + sel)
      5. Insère le maillon en base
      6. Retourne les hashs calculés pour stockage dans la transaction source

    Tout se passe dans la même transaction SQL → atomicité garantie.
    """
    previous_hash, last_sequence = get_last_chain_hash(db)
    new_sequence  = last_sequence + 1
    salt          = generate_chain_salt()

    data_hash  = compute_data_hash(payload)
    chain_hash = compute_chain_hash(payload, previous_hash, salt)

    db.execute(
        text("""
            INSERT INTO [OPERATION].[HashChain]
                ([TransactionId], [TransactionType], [SourceId],
                 [DataHash], [ChainHash], [PreviousHash], [Salt],
                 [Matricule], [DeviceId], [Sequence], [CreatedDate])
            VALUES
                (:txn_id, :txn_type, :src_id,
                 :data_hash, :chain_hash, :prev_hash, :salt,
                 :matricule, :device_id, :sequence, GETDATE())
        """),
        {
            "txn_id":     transaction_id,
            "txn_type":   transaction_type,
            "src_id":     source_id,
            "data_hash":  data_hash,
            "chain_hash": chain_hash,
            "prev_hash":  previous_hash,
            "salt":       salt,
            "matricule":  matricule,
            "device_id":  device_id,
            "sequence":   new_sequence
        }
    )

    return {
        "data_hash":    data_hash,
        "chain_hash":   chain_hash,
        "previous_hash": previous_hash,
        "sequence":     new_sequence
    }


def verify_full_chain(db: Session) -> dict:
    """
    Vérifie l'intégrité de toute la HashChain depuis le bloc genesis.

    Algorithme :
      - Lit tous les maillons dans l'ordre de séquence
      - Pour chaque maillon N :
          a. Recalcule chain_hash à partir de (data_hash, prev_hash, salt)
          b. Compare avec le chain_hash stocké
          c. Vérifie que prev_hash == chain_hash du maillon N-1
      - Si une rupture est détectée → retourne le numéro de séquence fautif

    Retourne un dict avec :
      - valid        : True si toute la chaîne est intègre
      - total        : nombre total de maillons vérifiés
      - broken_at    : séquence du premier maillon corrompu (None si valide)
      - error        : description de l'erreur (None si valide)
    """
    rows = db.execute(
        text("""
            SELECT [Sequence], [TransactionId], [TransactionType],
                   [DataHash], [ChainHash], [PreviousHash], [Salt],
                   [Matricule], [DeviceId]
            FROM [OPERATION].[HashChain]
            ORDER BY [Sequence] ASC
        """)
    ).fetchall()

    if not rows:
        return {"valid": True, "total": 0, "broken_at": None, "error": None}

    expected_previous = GENESIS_HASH

    for row in rows:
        # Vérification 1 : le previous_hash stocké correspond-il
        # au chain_hash du maillon précédent ?
        if row.PreviousHash != expected_previous:
            return {
                "valid":     False,
                "total":     len(rows),
                "broken_at": row.Sequence,
                "error":     (
                    f"Rupture de chaîne au maillon {row.Sequence} : "
                    f"previous_hash attendu={expected_previous[:16]}... "
                    f"trouvé={row.PreviousHash[:16]}..."
                )
            }

        # Vérification 2 : le chain_hash stocké peut-il être recalculé
        # à partir des données stockées ?
        # On reconstruit un payload minimal depuis DataHash pour la vérif.
        # En pratique on utilise verify_chain_hash avec le DataHash comme proxy.
        recomputed = compute_chain_hash(
            {"_hash": row.DataHash},   # Proxy : DataHash représente le payload
            row.PreviousHash,
            row.Salt
        )

        # Note : en production, on recalcule depuis la table source (Controle/Vente).
        # Ici on vérifie via le data_hash stocké (cohérence interne de la chaîne).
        if recomputed != row.ChainHash:
            return {
                "valid":     False,
                "total":     len(rows),
                "broken_at": row.Sequence,
                "error":     (
                    f"Hash corrompu au maillon {row.Sequence} "
                    f"(transaction {row.TransactionId[:8]}...) : "
                    f"hash recalculé différent du hash stocké"
                )
            }

        expected_previous = row.ChainHash   # Avancer dans la chaîne

    return {
        "valid":     True,
        "total":     len(rows),
        "broken_at": None,
        "error":     None
    }


def verify_single_transaction(
    db:             Session,
    transaction_id: str,
    payload:        dict
) -> dict:
    """
    Vérifie l'intégrité d'une seule transaction.

    Utilisé par le Back-Office à la réception d'une transaction :
      1. Récupère le maillon correspondant en base
      2. Recalcule le data_hash depuis le payload reçu
      3. Compare avec le data_hash stocké

    Retourne un dict avec valid, transaction_id et error.
    """
    row = db.execute(
        text("""
            SELECT [DataHash], [ChainHash], [PreviousHash], [Salt], [Sequence]
            FROM [OPERATION].[HashChain]
            WHERE [TransactionId] = :txn_id
        """),
        {"txn_id": transaction_id}
    ).fetchone()

    if not row:
        return {
            "valid":          False,
            "transaction_id": transaction_id,
            "error":          "Transaction introuvable dans la HashChain"
        }

    recomputed_data_hash = compute_data_hash(payload)

    if recomputed_data_hash != row.DataHash:
        return {
            "valid":          False,
            "transaction_id": transaction_id,
            "error":          (
                f"Data hash invalide pour la transaction {transaction_id[:8]}... "
                f"— falsification du contenu détectée"
            )
        }

    return {
        "valid":          True,
        "transaction_id": transaction_id,
        "sequence":       row.Sequence,
        "error":          None
    }