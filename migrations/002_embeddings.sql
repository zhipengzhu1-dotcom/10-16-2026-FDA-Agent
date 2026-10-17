CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS section_embeddings (
    citation text NOT NULL,
    effective_date date NOT NULL,
    model text NOT NULL,
    text_hash text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (citation, effective_date, model),
    FOREIGN KEY (citation, effective_date)
        REFERENCES reg_sections (citation, effective_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS query_embeddings (
    model text NOT NULL,
    query text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (model, query)
);
