CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS images (
 id BIGSERIAL PRIMARY KEY,
 sha256 TEXT NOT NULL,
 post_url TEXT NOT NULL DEFAULT '',
 phash BIT(64) NOT NULL,
 embedding VECTOR(512) NOT NULL,
 thumbnail BYTEA NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(sha256, post_url)
);
CREATE INDEX IF NOT EXISTS images_embedding_idx ON images USING hnsw (embedding vector_cosine_ops);
