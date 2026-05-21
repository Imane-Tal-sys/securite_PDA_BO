import uuid
from sqlalchemy.orm    import Session
from sqlalchemy        import text
from fastapi           import HTTPException, status
from datetime          import datetime, timezone

from .schemas          import VenteRequest, VenteResponse, OperationPayload
from .anti_replay      import assert_not_duplicate
from app.integrite.integrite_service import IntegriteService


class VenteService:

    def __init__(self):
        self.integrite_service = IntegriteService()

    def process_vente(
        self,
        payload_obj: OperationPayload,
        db:          Session
    ) -> VenteResponse:
        """
        Traite une opération de vente de billet reçue du PDA.
        """
        data = payload_obj.data

        # ---- 1. Anti-rejeu -------------------------------------------
        assert_not_duplicate(db, payload_obj.transaction_id)

        # ---- 2. Validation métier ------------------------------------
        self._validate_vente(data)

        # ---- 3. Génération numéro de billet --------------------------
        numero_billet = self._generate_numero_billet()
        data["numero_billet"] = numero_billet

        # ---- 4. INSERT OPERATION.VenteBillet -------------------------
        vente_id = self._insert_vente(data, db)

        # ---- 5. Scellement HashChain ---------------------------------
        chain_entry = self.integrite_service.seal_transaction(
            db               = db,
            transaction_id   = payload_obj.transaction_id,
            transaction_type = "vente",
            source_id        = vente_id,
            payload          = data,
            matricule        = payload_obj.matricule,
            device_id        = payload_obj.device_id
        )

        # ---- 6. Commit final ----------------------------------------
        db.commit()

        return VenteResponse(
            success          = True,
            vente_id         = vente_id,
            numero_billet    = numero_billet,
            transaction_id   = payload_obj.transaction_id,
            chain_sequence   = chain_entry.sequence,
            message          = (
                f"Vente enregistrée — billet {numero_billet} "
                f"montant: {data['montant']} MAD "
                f"[séquence HashChain: {chain_entry.sequence}]"
            )
        )

    # ------------------------------------------------------------------
    # Validation métier
    # ------------------------------------------------------------------

    def _validate_vente(self, data: dict) -> None:
        """
        Valide les données métier d'une vente.
        """
        champs_obligatoires = [
            "mission_id", "liaison_id", "niveau_confort_id",
            "niveau_prix_id", "bareme_id", "titre_reduction", "motif"
        ]
        for champ in champs_obligatoires:
            if data.get(champ) is None:
                raise HTTPException(
                    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail      = f"Champ obligatoire manquant : {champ}"
                )

        montant = data.get("montant", 0)
        if montant <= 0:
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = f"Le montant doit être positif (reçu : {montant})"
            )

        nb_voyageurs = data.get("nombre_voyageurs", 0)
        if not (1 <= nb_voyageurs <= 100):
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = f"nombre_voyageurs invalide : {nb_voyageurs} (1-100)"
            )

        if montant < nb_voyageurs:
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = (
                    f"Montant incohérent : {montant} MAD "
                    f"pour {nb_voyageurs} voyageur(s)"
                )
            )

    # ------------------------------------------------------------------
    # Génération numéro de billet
    # ------------------------------------------------------------------

    def _generate_numero_billet(self) -> str:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        uuid_part = str(uuid.uuid4()).replace("-", "")[:8].upper()
        return f"BIL-{date_part}-{uuid_part}"

    # ------------------------------------------------------------------
    # INSERT SQL
    # ------------------------------------------------------------------

    def _insert_vente(self, data: dict, db: Session) -> int:
        result = db.execute(
            text("""
                INSERT INTO [OPERATION].[VenteBillet]
                    ([NumeroBillet], [DateOperation], [Montant], [NombreVoyageurs],
                     [NiveauConfortId], [LiaisonId], [NiveauPrixId], [TitreReduction],
                     [MissionId], [Motif], [NumeroMotif], [BaremeId], [BilletUuid],
                     [DossierVoyageSIV], [CodeDossierVoyage],
                     [StatutSynchronisationSIV], [GammeId], [IsCancelled],
                     [NumeroPlace], [NumeroVoiture], [StatutOperationPDA],
                     [NumeroTransaction], [CreatedDate], [LastModifiedDate])
                OUTPUT INSERTED.Id
                VALUES
                    (:numero_billet, :date_operation, :montant, :nombre_voyageurs,
                     :niveau_confort_id, :liaison_id, :niveau_prix_id, :titre_reduction,
                     :mission_id, :motif, :numero_motif, :bareme_id, :billet_uuid,
                     :dossier_voyage_siv, :code_dossier_voyage,
                     :statut_synchro_siv, :gamme_id, :is_cancelled,
                     :numero_place, :numero_voiture, :statut_operation_pda,
                     :numero_transaction, GETDATE(), GETDATE())
            """),
            {
                "numero_billet":          data.get("numero_billet"),
                "date_operation":         data.get("date_operation"),
                "montant":                data.get("montant"),
                "nombre_voyageurs":       data.get("nombre_voyageurs"),
                "niveau_confort_id":      data.get("niveau_confort_id"),
                "liaison_id":             data.get("liaison_id"),
                "niveau_prix_id":         data.get("niveau_prix_id"),
                "titre_reduction":        data.get("titre_reduction"),
                "mission_id":             data.get("mission_id"),
                "motif":                  data.get("motif"),
                "numero_motif":           data.get("numero_motif"),
                "bareme_id":              data.get("bareme_id"),
                "billet_uuid":            str(uuid.uuid4()),
                "dossier_voyage_siv":     data.get("dossier_voyage_siv"),
                "code_dossier_voyage":    data.get("code_dossier_voyage"),
                "statut_synchro_siv":     data.get("statut_synchronisation_siv", 0),
                "gamme_id":               data.get("gamme_id"),
                "is_cancelled":           data.get("is_cancelled", False),
                "numero_place":           data.get("numero_place"),
                "numero_voiture":         data.get("numero_voiture"),
                "statut_operation_pda":   data.get("statut_operation_pda", 1),
                "numero_transaction":     data.get("numero_transaction"),
            }
        )
        return result.fetchone()[0]