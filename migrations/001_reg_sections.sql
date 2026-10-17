CREATE TABLE IF NOT EXISTS reg_sections (
    citation text NOT NULL,
    effective_date date NOT NULL,
    source text NOT NULL,
    title text NOT NULL,
    text text NOT NULL,
    url text NOT NULL,
    PRIMARY KEY (citation, effective_date)
);
