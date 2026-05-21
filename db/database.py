import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = os.getenv("DB_HOST", "sqlserver")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_NAME = os.getenv("DB_NAME", "PDA_DB_PB")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASS = os.getenv("SA_PASSWORD", "YourStrong@Passw0rd")

# Chaîne de connexion ODBC pour SQL Server
DATABASE_URL = (
    f"mssql+pyodbc://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&TrustServerCertificate=yes"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dépendance FastAPI qui fournit une session DB par requête.
    La session est fermée automatiquement après la requête (finally).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()