'schemas.py'
from pydantic import BaseModel, Field
from typing   import Optional
from datetime import datetime


# -----------------------------------------------------------------------
# Contrôle de billet
# -----------------------------------------------------------------------

class ControleRequest(BaseModel):
    """
    Payload envoyé par le PDA lors d'un contrôle de billet.
    Correspond aux colonnes de OPERATION.Controle.
    """
    # Identifiants de mission et billet
    mission_id:          int
    numero_billet:       Optional[str]  = None
    code_2d_controle:    Optional[str]  = None   # Contenu du QR/code-barres scanné

    # Localisation du contrôle
    gare_depart_id:      Optional[int]  = None
    gare_arrivee_id:     Optional[int]  = None
    gare_controle_id:    Optional[int]  = None
    gamme_id:            Optional[int]  = None
    niveau_confort_id:   Optional[int]  = None

    # Résultat
    tarif:               Optional[str]  = None
    resultat_controle:   Optional[str]  = None   # 'OK', 'KO', 'FR' (fraude)
    type_controle:       Optional[str]  = None   # 'BO' (bord), 'QI' (quai)
    message_controle:    Optional[str]  = None

    # Données complémentaires
    code_dossier:           Optional[str]  = None
    profil_demographique_id: Optional[int] = None

    # Métadonnées sécurité (ajoutées par payload_builder, pas saisies par l'agent)
    device_id:           str
    matricule:           str
    transaction_id:      Optional[str] = None   # UUID généré côté PDA
    date_heure_controle: Optional[datetime] = None


class ControleResponse(BaseModel):
    """Réponse du Back-Office après traitement d'un contrôle."""
    success:        bool
    controle_id:    Optional[int] = None
    transaction_id: str
    chain_sequence: Optional[int] = None
    message:        str


# -----------------------------------------------------------------------
# Vente de billet
# -----------------------------------------------------------------------

class VenteRequest(BaseModel):
    """
    Payload envoyé par le PDA lors d'une vente de billet.
    Correspond aux colonnes de OPERATION.VenteBillet.
    """
    # Détails de la vente
    mission_id:          int
    liaison_id:          int
    niveau_confort_id:   int
    niveau_prix_id:      int
    bareme_id:           int
    gamme_id:            Optional[int]   = None

    # Montant et voyageurs
    montant:             float
    nombre_voyageurs:    int              = Field(ge=1, le=100)

    # Réduction et motif
    titre_reduction:     str
    motif:               str
    numero_motif:        str

    # Place et voiture (si réservation)
    numero_place:        Optional[int]   = None
    numero_voiture:      Optional[int]   = None

    # Synchronisation SIV (Système d'Information Voyageurs)
    dossier_voyage_siv:  Optional[int]   = None
    code_dossier_voyage: Optional[str]   = None

    # Métadonnées sécurité
    device_id:           str
    matricule:           str
    transaction_id:      Optional[str]   = None
    date_operation:      Optional[datetime] = None


class VenteResponse(BaseModel):
    """Réponse du Back-Office après traitement d'une vente."""
    success:          bool
    vente_id:         Optional[int] = None
    numero_billet:    Optional[str] = None
    transaction_id:   str
    chain_sequence:   Optional[int] = None
    message:          str


# -----------------------------------------------------------------------
# Payload chiffré générique (sortie du payload_builder, entrée du Crypto)
# -----------------------------------------------------------------------

class OperationPayload(BaseModel):
    """Structure normalisée d'un payload avant chiffrement."""
    operation_type: str       # 'controle' ou 'vente'
    transaction_id: str       # UUID v4 unique anti-rejeu
    timestamp:      str       # ISO 8601
    device_id:      str
    matricule:      str
    data:           dict      # Données métier de l'opération