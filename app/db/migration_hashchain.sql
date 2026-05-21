USE [PDA_DB_PB];

CREATE TABLE [OPERATION].[HashChain](
    [Id]              [int] IDENTITY(1,1) NOT NULL,

    -- Référence vers la transaction source
    [TransactionId]   [nvarchar](100) NOT NULL,  -- UUID de la transaction
    [TransactionType] [nvarchar](20)  NOT NULL,  -- 'controle' ou 'vente'
    [SourceId]        [int]           NOT NULL,  -- ControleId ou VenteBilletId

    -- Données d'intégrité
    [DataHash]        [nvarchar](64)  NOT NULL,  -- SHA-256 du payload seul
    [ChainHash]       [nvarchar](64)  NOT NULL,  -- SHA-256(payload + hash_precedent + sel)
    [PreviousHash]    [nvarchar](64)  NOT NULL,  -- hash_chain du maillon N-1
    [Salt]            [nvarchar](64)  NOT NULL,  -- sel aléatoire unique par maillon

    -- Contexte de l'opération
    [Matricule]       [nvarchar](50)  NOT NULL,  -- Agent qui a effectué la transaction
    [DeviceId]        [nvarchar](100) NOT NULL,  -- Terminal source
    [Sequence]        [int]           NOT NULL,  -- Numéro de séquence dans la chaîne

    [CreatedDate]     [datetime]      NOT NULL DEFAULT (GETDATE()),

    CONSTRAINT [PK_HashChain] PRIMARY KEY CLUSTERED ([Id] ASC),
    CONSTRAINT [UQ_TransactionId] UNIQUE ([TransactionId]),
    CONSTRAINT [UQ_Sequence] UNIQUE ([Sequence])
) ON [PRIMARY];

-- Index pour la vérification rapide de la chaîne
CREATE INDEX [IX_HashChain_Sequence]
    ON [OPERATION].[HashChain] ([Sequence] ASC);

CREATE INDEX [IX_HashChain_ChainHash]
    ON [OPERATION].[HashChain] ([ChainHash] ASC);