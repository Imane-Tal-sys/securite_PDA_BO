'anti_replay.py'
from sqlalchemy.orm import Session
from sqlalchemy     import text
from fastapi        import HTTPException, status


def is_duplicate_transaction(db: Session, transaction_id: str) -> bool:
    """
    Vérifie si un transaction_id a déjà été traité.

    Cherche dans OPERATION.HashChain qui est la source de vérité
    des transactions reçues (toute transaction scellée est unique).
    """
    row = db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM [OPERATION].[HashChain]
            WHERE [TransactionId] = :txn_id
        """),
        {"txn_id": transaction_id}
    ).fetchone()

    return row.cnt > 0


def assert_not_duplicate(db: Session, transaction_id: str) -> None:
    """
    Lève HTTP 409 si la transaction a déjà été traitée.
    À appeler au début de chaque endpoint d'opération.
    """
    if is_duplicate_transaction(db, transaction_id):
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = (
                f"Transaction {transaction_id[:8]}... déjà traitée. "
                "Possible attaque par rejeu détectée."
            )
        )