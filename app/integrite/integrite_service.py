'app/integrite/integrite_service.py'
from sqlalchemy.orm import Session

from .hash  import compute_data_hash, verify_data_hash
from .hashchain     import (
    add_to_chain,
    verify_full_chain,
    verify_single_transaction
)
from .schemas import (
    HashChainEntry,
    ChainVerificationResult,
    TransactionVerificationResult
)


class IntegriteService:
    """
    Service d'intégrité des transactions PDA.

    Deux responsabilités :
      1. Sceller chaque transaction dans la HashChain à l'arrivée
      2. Vérifier l'intégrité de la chaîne (à la demande ou en tâche planifiée)
    """

    # ------------------------------------------------------------------
    # SCELLEMENT D'UNE TRANSACTION
    # ------------------------------------------------------------------

    def seal_transaction(
        self,
        db:               Session,
        transaction_id:   str,
        transaction_type: str,   # 'controle' ou 'vente'
        source_id:        int,
        payload:          dict,
        matricule:        str,
        device_id:        str
    ) -> HashChainEntry:
        """
        Scelle une transaction dans la HashChain.

        Appelé par le Back-Office immédiatement après avoir déchiffré
        et validé une transaction (après les vérifications Crypto/Auth).

        Le scellement est atomique avec l'insertion en base de la
        transaction source : si l'un échoue, les deux sont annulés
        (rollback SQL via la même session).
        """
        result = add_to_chain(
            db               = db,
            transaction_id   = transaction_id,
            transaction_type = transaction_type,
            source_id        = source_id,
            payload          = payload,
            matricule        = matricule,
            device_id        = device_id
        )

        return HashChainEntry(
            transaction_id = transaction_id,
            data_hash      = result["data_hash"],
            chain_hash     = result["chain_hash"],
            previous_hash  = result["previous_hash"],
            sequence       = result["sequence"]
        )

    # ------------------------------------------------------------------
    # VÉRIFICATION D'UNE TRANSACTION
    # ------------------------------------------------------------------

    def verify_transaction(
        self,
        db:             Session,
        transaction_id: str,
        payload:        dict
    ) -> TransactionVerificationResult:
        """
        Vérifie qu'une transaction stockée n'a pas été modifiée en base.

        Recalcule le data_hash depuis le payload et le compare
        avec le data_hash stocké dans HashChain.

        Utilisé pour l'audit à la demande ou lors de contrôles de supervision.
        """
        result = verify_single_transaction(db, transaction_id, payload)

        return TransactionVerificationResult(
            valid          = result["valid"],
            transaction_id = result["transaction_id"],
            sequence       = result.get("sequence"),
            error          = result.get("error")
        )

    # ------------------------------------------------------------------
    # VÉRIFICATION DE TOUTE LA CHAÎNE
    # ------------------------------------------------------------------

    def verify_chain(self, db: Session) -> ChainVerificationResult:
        """
        Vérifie l'intégrité de toute la HashChain depuis le genesis.

        Opération coûteuse (scan complet) — à appeler en tâche planifiée
        (ex: toutes les 6 heures) ou manuellement par l'administrateur.

        Si la vérification échoue, une alerte doit être déclenchée
        immédiatement (voir module Audit, Phase 8).
        """
        result = verify_full_chain(db)

        return ChainVerificationResult(
            valid      = result["valid"],
            total      = result["total"],
            broken_at  = result.get("broken_at"),
            error      = result.get("error")
        )

    # ------------------------------------------------------------------
    # HASH SEUL (utilitaire)
    # ------------------------------------------------------------------

    def compute_payload_hash(self, payload: dict) -> str:
        """
        Calcule le hash SHA-256 d'un payload sans l'insérer en base.
        Utilitaire pour les tests et la vérification côté PDA avant envoi.
        """
        return compute_data_hash(payload)