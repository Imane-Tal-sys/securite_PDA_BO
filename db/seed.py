"""
Exécuter une fois pour initialiser les données de test :
  python db/seed.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.auth.password import generate_salt, hash_password
from app.db.database import SessionLocal
from sqlalchemy import text

def seed():
    db = SessionLocal()

    salt     = generate_salt()
    password = hash_password("Agent123!", salt)
    stored   = f"{salt}${password}"

    db.execute(
        text("""
            UPDATE [Habilitation].[Utilisateur]
            SET [Password] = :pwd
            WHERE [Matricule] = 'AG001'
        """),
        {"pwd": stored}
    )
    db.commit()
    db.close()
    print(f"[SEED] Mot de passe initialisé pour AG001")
    print(f"[SEED] Sel : {salt[:8]}...")
    print(f"[SEED] Hash : {password[:16]}...")

if __name__ == "__main__":
    seed()