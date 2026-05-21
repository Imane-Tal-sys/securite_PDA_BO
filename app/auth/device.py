'device.py'
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime


def is_device_registered(
    db: Session,
    matricule: str,
    device_id: str
) -> bool:
    """
    Vérifie si le terminal (device_id) est autorisé pour cet agent (matricule).

    Requête sur Habilitation.DeviceUtilisateur :
      - UQ_MatriculeUtilisateur garantit un seul device par matricule
      - Si le couple (matricule, device_id) n'existe pas → accès refusé

    Principe Zero Trust : le réseau ET le terminal sont suspects par défaut.
    """
    result = db.execute(
        text("""
            SELECT COUNT(*) as cnt
            FROM [Habilitation].[DeviceUtilisateur]
            WHERE [MatriculeUtilisateur] = :matricule
              AND [DeviceId] = :device_id
        """),
        {"matricule": matricule, "device_id": device_id}
    ).fetchone()

    return result.cnt > 0


def register_device(
    db: Session,
    matricule: str,
    device_id: str
) -> bool:
    """
    Enregistre un nouveau terminal pour un agent.
    Appelé par l'administrateur sécurité (pas par le PDA lui-même).
    Retourne False si le matricule a déjà un device enregistré.
    """
    # Vérifier qu'il n'existe pas déjà (contrainte UQ_MatriculeUtilisateur)
    if is_device_registered(db, matricule, device_id):
        return False

    db.execute(
        text("""
            INSERT INTO [Habilitation].[DeviceUtilisateur]
                ([MatriculeUtilisateur], [DeviceId], [CreatedDate], [LastModifiedDate])
            VALUES
                (:matricule, :device_id, GETDATE(), GETDATE())
        """),
        {"matricule": matricule, "device_id": device_id}
    )
    db.commit()
    return True


def update_device(
    db: Session,
    matricule: str,
    new_device_id: str
) -> None:
    """
    Met à jour le device_id d'un agent (remplacement de terminal).
    Opération réservée à l'administrateur sécurité.
    """
    db.execute(
        text("""
            UPDATE [Habilitation].[DeviceUtilisateur]
            SET [DeviceId] = :new_device_id,
                [LastModifiedDate] = GETDATE()
            WHERE [MatriculeUtilisateur] = :matricule
        """),
        {"matricule": matricule, "new_device_id": new_device_id}
    )
    db.commit()