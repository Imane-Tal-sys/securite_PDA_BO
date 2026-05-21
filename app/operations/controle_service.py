from sqlalchemy.orm    import Session
from sqlalchemy        import text

from fastapi           import HTTPException, status
from datetime          import datetime, timezone

from .schemas          import ControleRequest, ControleResponse, OperationPayload
from .anti_replay      import assert_not_duplicate
from app.integrite.integrite_service import IntegriteService

# Résultats de contrôle valides
RESULTATS_VALIDES = {"OK", "KO", "FR", "AB", "NP"}
# OK=valide, KO=invalide, FR=fraude, AB=absent, NP=non présenté

# Types de contrôle valides
TYPES_VALIDES = {"BO", "QI", "AC"}
# BO=bord train, QI=quai, AC=accès


class ControleService:

    def __init__(self):
        self.integrite_service = IntegriteService()

    def process_controle(
        self,
        payload_obj: OperationPayload,
        db:          Session
    ) -> ControleResponse:
        """
        Traite une opération de contrôle de billet reçue du PDA.
        """
        data = payload_obj.data

        # ---- 1. Anti-rejeu --------------------------------------------
        assert_not_duplicate(db, payload_obj.transaction_id)

        # ---- 2. Validation métier ------------------------------------
        self._validate_controle(data)

        # ---- 3. INSERT OPERATION.Controle ----------------------------
        controle_id = self._insert_controle(data, db)

        # ---- 4. Scellement HashChain (même session DB = atomique) ----
        chain_entry = self.integrite_service.seal_transaction(
            db               = db,
            transaction_id   = payload_obj.transaction_id,
            transaction_type = "controle",
            source_id        = controle_id,
            payload          = data,
            matricule        = payload_obj.matricule,
            device_id        = payload_obj.device_id
        )

        # ---- 5. Commit final -----------------------------------------
        db.commit()

        return ControleResponse(
            success        = True,
            controle_id    = controle_id,
            transaction_id = payload_obj.transaction_id,
            chain_sequence = chain_entry.sequence,
            message        = (
                f"Contrôle enregistré — billet {data.get('numero_billet', 'N/A')} "
                f"résultat: {data.get('resultat_controle', '?')} "
                f"[séquence HashChain: {chain_entry.sequence}]"
            )
        )

    # ------------------------------------------------------------------
    # Validation métier
    # ------------------------------------------------------------------

    def _validate_controle(self, data: dict) -> None:
        """
        Valide les données métier d'un contrôle.
        """
        if not data.get("mission_id"):
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = "mission_id est obligatoire"
            )

        if not data.get("numero_billet") and not data.get("code_2d_controle"):
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = "numero_billet ou code_2d_controle est obligatoire"
            )

        resultat = data.get("resultat_controle")
        if resultat and resultat not in RESULTATS_VALIDES:
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = f"resultat_controle invalide : '{resultat}'. "
                              f"Valeurs acceptées : {RESULTATS_VALIDES}"
            )

        type_ctrl = data.get("type_controle")
        if type_ctrl and type_ctrl not in TYPES_VALIDES:
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail      = f"type_controle invalide : '{type_ctrl}'. "
                              f"Valeurs acceptées : {TYPES_VALIDES}"
            )

    # ------------------------------------------------------------------
    # INSERT SQL
    # ------------------------------------------------------------------

    def _insert_controle(self, data: dict, db: Session) -> int:
        """
        Insère un enregistrement dans OPERATION.Controle.
        Retourne le ControleId généré (IDENTITY).
        """
        result = db.execute(
            text("""
                INSERT INTO [OPERATION].[Controle]
                    ([MissionId], [NumeroBillet], [GareDepartId], [GareArriveeId],
                     [GammeId], [NiveauConfortId], [Tarif], [MessageControle],
                     [ResultatControle], [DateHeureControle], [TypeControle],
                     [Code2DControle], [GareControleId], [CodeDossier],
                     [ProfilDemographiqueId], [CreatedDate], [LastModifiedDate])
                OUTPUT INSERTED.ControleId
                VALUES
                    (:mission_id, :numero_billet, :gare_depart_id, :gare_arrivee_id,
                     :gamme_id, :niveau_confort_id, :tarif, :message_controle,
                     :resultat_controle, :date_heure_controle, :type_controle,
                     :code_2d_controle, :gare_controle_id, :code_dossier,
                     :profil_demographique_id, GETDATE(), GETDATE())
            """),
            {
                "mission_id":              data.get("mission_id"),
                "numero_billet":           data.get("numero_billet"),
                "gare_depart_id":          data.get("gare_depart_id"),
                "gare_arrivee_id":         data.get("gare_arrivee_id"),
                "gamme_id":                data.get("gamme_id"),
                "niveau_confort_id":       data.get("niveau_confort_id"),
                "tarif":                   data.get("tarif"),
                "message_controle":        data.get("message_controle"),
                "resultat_controle":       data.get("resultat_controle"),
                "date_heure_controle":     data.get("date_heure_controle"),
                "type_controle":           data.get("type_controle"),
                "code_2d_controle":        data.get("code_2d_controle"),
                "gare_controle_id":        data.get("gare_controle_id"),
                "code_dossier":            data.get("code_dossier"),
                "profil_demographique_id": data.get("profil_demographique_id"),
            }
        )
        row = result.fetchone()
        return row[0]