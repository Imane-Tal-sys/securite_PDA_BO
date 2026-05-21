'app/integrite/schemas.py'
from pydantic import BaseModel
from typing import Optional


class HashChainEntry(BaseModel):
    """Résultat de l'ajout d'un maillon dans la HashChain."""
    transaction_id: str
    data_hash:      str   # SHA-256(payload seul)
    chain_hash:     str   # SHA-256(payload + prev_hash + sel)
    previous_hash:  str
    sequence:       int


class ChainVerificationResult(BaseModel):
    """Résultat d'une vérification de la HashChain complète."""
    valid:      bool
    total:      int
    broken_at:  Optional[int]   # Numéro de séquence du maillon corrompu
    error:      Optional[str]


class TransactionVerificationResult(BaseModel):
    """Résultat de la vérification d'une seule transaction."""
    valid:          bool
    transaction_id: str
    sequence:       Optional[int] = None
    error:          Optional[str] = None