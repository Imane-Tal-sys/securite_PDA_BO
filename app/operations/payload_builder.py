'payload_builder.py'
import uuid
from datetime import datetime, timezone
from .schemas import ControleRequest, VenteRequest, OperationPayload


def build_controle_payload(
    request:   ControleRequest,
    matricule: str,
    device_id: str
) -> OperationPayload:
    """
    Construit le payload JSON normalisé pour un contrôle de billet.

    Ajoute automatiquement :
      - transaction_id : UUID v4 unique (anti-rejeu)
      - timestamp      : heure UTC de création du payload
      - device_id      : identifiant du terminal PDA
      - matricule      : agent effectuant le contrôle

    La date_heure_controle est fixée ici si non fournie —
    elle représente l'heure réelle du contrôle terrain.
    """
    txn_id = str(uuid.uuid4())
    now    = datetime.now(timezone.utc)

    data = {
        "mission_id":            request.mission_id,
        "numero_billet":         request.numero_billet,
        "code_2d_controle":      request.code_2d_controle,
        "gare_depart_id":        request.gare_depart_id,
        "gare_arrivee_id":       request.gare_arrivee_id,
        "gare_controle_id":      request.gare_controle_id,
        "gamme_id":              request.gamme_id,
        "niveau_confort_id":     request.niveau_confort_id,
        "tarif":                 request.tarif,
        "resultat_controle":     request.resultat_controle,
        "type_controle":         request.type_controle,
        "message_controle":      request.message_controle,
        "code_dossier":          request.code_dossier,
        "profil_demographique_id": request.profil_demographique_id,
        "date_heure_controle":   (
            request.date_heure_controle.isoformat()
            if request.date_heure_controle
            else now.isoformat()
        ),
    }

    return OperationPayload(
        operation_type = "controle",
        transaction_id = txn_id,
        timestamp      = now.isoformat(),
        device_id      = device_id,
        matricule      = matricule,
        data           = data
    )


def build_vente_payload(
    request:   VenteRequest,
    matricule: str,
    device_id: str
) -> OperationPayload:
    """
    Construit le payload JSON normalisé pour une vente de billet.

    Génère aussi un numéro de transaction unique pour le billet
    (NumeroTransaction dans VenteBillet).
    """
    txn_id     = str(uuid.uuid4())
    numero_txn = f"TXN-{now_str()}-{txn_id[:8].upper()}"
    now        = datetime.now(timezone.utc)

    data = {
        "mission_id":          request.mission_id,
        "liaison_id":          request.liaison_id,
        "niveau_confort_id":   request.niveau_confort_id,
        "niveau_prix_id":      request.niveau_prix_id,
        "bareme_id":           request.bareme_id,
        "gamme_id":            request.gamme_id,
        "montant":             request.montant,
        "nombre_voyageurs":    request.nombre_voyageurs,
        "titre_reduction":     request.titre_reduction,
        "motif":               request.motif,
        "numero_motif":        request.numero_motif,
        "numero_place":        request.numero_place,
        "numero_voiture":      request.numero_voiture,
        "dossier_voyage_siv":  request.dossier_voyage_siv,
        "code_dossier_voyage": request.code_dossier_voyage,
        "statut_synchronisation_siv": 0,   # 0 = en attente de synchro SIV
        "statut_operation_pda":       1,   # 1 = créée sur PDA
        "numero_transaction":  numero_txn,
        "is_cancelled":        False,
        "date_operation":      (
            request.date_operation.isoformat()
            if request.date_operation
            else now.isoformat()
        ),
    }

    return OperationPayload(
        operation_type = "vente",
        transaction_id = txn_id,
        timestamp      = now.isoformat(),
        device_id      = device_id,
        matricule      = matricule,
        data           = data
    )


def now_str() -> str:
    """Retourne la date courante au format YYYYMMDD pour les numéros de transaction."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")