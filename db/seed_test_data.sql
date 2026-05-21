--seed_test_data.sql
USE [PDA_DB_PB];

-- Mot de passe "Agent123!" hashé : sel = "abcd1234ef" (exemple)
-- SHA-256("Agent123!" + "abcd1234ef") = à recalculer avec generate_salt() + hash_password()
-- Pour le test, on insère directement via le script Python seed.py ci-dessous

-- Agent de test
INSERT INTO [Habilitation].[Utilisateur]
    ([Matricule],[Nom],[Prenom],[CIN],[Etat],[Password],
     [IsFirstConnexion],[StatutUtilisateurId],[EntiteId],
     [CreatedDate],[LastModifiedDate])
VALUES
    ('AG001','BEN ALI','Youssef','AB123456', 1,
     'PLACEHOLDER_REPLACED_BY_SEED',
     0, 1, 3,
     GETDATE(), GETDATE());

-- Terminal autorisé pour AG001
INSERT INTO [Habilitation].[DeviceUtilisateur]
    ([MatriculeUtilisateur],[DeviceId],[CreatedDate],[LastModifiedDate])
VALUES
    ('AG001','PDA-DEVICE-001', GETDATE(), GETDATE());