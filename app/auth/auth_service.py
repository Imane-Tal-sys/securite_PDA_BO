'auth_service.py'
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status
from datetime import datetime, timezone

from .password import hash_password, verify_password, generate_salt
from .device   import is_device_registered
from .session  import create_session
from .schemas import LoginRequest, LoginResponse, ChangePasswordRequest

MAX_ATTEMPTS = 3   # Nombre maximal de tentatives avant blocage


class AuthService:

    # ------------------------------------------------------------------
    # LOGIN PRINCIPAL
    # ------------------------------------------------------------------

    def login(self, request: LoginRequest, db: Session) -> LoginResponse:
        """
        Authentifie un agent PDA en 5 vérifications successives :
          1. Le matricule existe-t-il en base ?
          2. Le compte est-il actif (Etat = 1) ?
          3. Le nombre de tentatives échouées est-il dépassé ?
          4. Le mot de passe est-il correct ?
          5. Le terminal (device_id) est-il autorisé pour cet agent ?
        """

        # ---- 1. Récupérer l'utilisateur --------------------------------
        user = self._get_user(request.matricule, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Matricule ou mot de passe incorrect"
            )

        # ---- 2. Compte actif ? -----------------------------------------
        if not user["Etat"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte désactivé. Contactez l'administrateur."
            )

        # ---- 3. Trop de tentatives échouées ? --------------------------
        attempts = user["ConnectionAttemptsNumber"] or 0
        if attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Compte bloqué après {MAX_ATTEMPTS} tentatives. "
                       "Contactez l'administrateur."
            )

        # ---- 4. Vérification du mot de passe ---------------------------
        # Le champ Password stocke "sel$hash" (séparateur $)
        stored = user["Password"]
        if "$" not in stored:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Format de mot de passe invalide en base"
            )

        salt, stored_hash = stored.split("$", 1)

        if not verify_password(request.password, salt, stored_hash):
            # Incrémenter le compteur de tentatives
            self._increment_attempts(request.matricule, db)
            remaining = MAX_ATTEMPTS - (attempts + 1)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Mot de passe incorrect. "
                       f"Tentatives restantes : {max(remaining, 0)}"
            )

        # ---- 5. Device Binding -----------------------------------------
        if not is_device_registered(db, request.matricule, request.device_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Terminal non autorisé pour cet agent. "
                       "Contactez l'administrateur sécurité."
            )

        # ---- Succès : réinitialiser le compteur et créer la session ----
        self._reset_attempts(request.matricule, db)
        self._update_last_connection(request.matricule, db)

        session = create_session(
            matricule = request.matricule,
            role_id   = user["RoleId"] or 0,
            device_id = request.device_id
        )

        return LoginResponse(
            access_token   = session["access_token"],
            session_key    = session["session_key"],
            expires_at     = session["expires_at"],
            token_type     = session["token_type"],
            is_first_login = bool(user["IsFirstConnexion"])
        )

    # ------------------------------------------------------------------
    # CHANGEMENT DE MOT DE PASSE
    # ------------------------------------------------------------------

    def change_password(
        self,
        request: ChangePasswordRequest,
        db: Session
    ) -> dict:
        """
        Change le mot de passe d'un agent.
        Obligatoire à la première connexion (IsFirstConnexion = 1).

        Le nouveau mot de passe est hashé avec un nouveau sel aléatoire.
        """
        user = self._get_user(request.matricule, db)
        if not user:
            raise HTTPException(status_code=404, detail="Agent introuvable")

        # Vérifier l'ancien mot de passe
        salt, stored_hash = user["Password"].split("$", 1)
        if not verify_password(request.old_password, salt, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ancien mot de passe incorrect"
            )

        # Vérifier que le nouveau mot de passe est différent
        new_hash_check = hash_password(request.new_password, salt)
        if new_hash_check == stored_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le nouveau mot de passe doit être différent de l'ancien"
            )

        # Générer un nouveau sel et hasher le nouveau mot de passe
        new_salt     = generate_salt()
        new_hash     = hash_password(request.new_password, new_salt)
        new_password = f"{new_salt}${new_hash}"

        db.execute(
            text("""
                UPDATE [Habilitation].[Utilisateur]
                SET [Password]                 = :new_password,
                    [IsFirstConnexion]         = 0,
                    [DateModificationPassword] = GETDATE(),
                    [LastModifiedDate]         = GETDATE()
                WHERE [Matricule] = :matricule
            """),
            {"new_password": new_password, "matricule": request.matricule}
        )
        db.commit()

        return {"success": True, "message": "Mot de passe modifié avec succès"}

    # ------------------------------------------------------------------
    # MÉTHODES PRIVÉES
    # ------------------------------------------------------------------

    def _get_user(self, matricule: str, db: Session) -> dict | None:
        """Récupère les données d'un utilisateur depuis Habilitation.Utilisateur."""
        row = db.execute(
            text("""
                SELECT [UtilisateurId], [Matricule], [Nom], [Prenom],
                       [Password], [Etat], [IsFirstConnexion],
                       [RoleId], [StatutUtilisateurId],
                       [ConnectionAttemptsNumber], [LastConnectionAttemptDate]
                FROM [Habilitation].[Utilisateur]
                WHERE [Matricule] = :matricule
            """),
            {"matricule": matricule}
        ).fetchone()

        if not row:
            return None
        return dict(row._mapping)

    def _increment_attempts(self, matricule: str, db: Session) -> None:
        """Incrémente ConnectionAttemptsNumber et note l'heure de la tentative."""
        db.execute(
            text("""
                UPDATE [Habilitation].[Utilisateur]
                SET [ConnectionAttemptsNumber] =
                        ISNULL([ConnectionAttemptsNumber], 0) + 1,
                    [LastConnectionAttemptDate] = GETDATE(),
                    [LastModifiedDate]          = GETDATE()
                WHERE [Matricule] = :matricule
            """),
            {"matricule": matricule}
        )
        db.commit()

    def _reset_attempts(self, matricule: str, db: Session) -> None:
        """Remet le compteur à 0 après une connexion réussie."""
        db.execute(
            text("""
                UPDATE [Habilitation].[Utilisateur]
                SET [ConnectionAttemptsNumber]  = 0,
                    [LastConnectionAttemptDate] = NULL,
                    [LastModifiedDate]          = GETDATE()
                WHERE [Matricule] = :matricule
            """),
            {"matricule": matricule}
        )
        db.commit()

    def _update_last_connection(self, matricule: str, db: Session) -> None:
        """Met à jour DateConnection après chaque connexion réussie."""
        db.execute(
            text("""
                UPDATE [Habilitation].[Utilisateur]
                SET [DateConnection]   = CAST(GETDATE() AS DATE),
                    [LastModifiedDate] = GETDATE()
                WHERE [Matricule] = :matricule
            """),
            {"matricule": matricule}
        )
        db.commit()