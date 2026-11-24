-- COUPLED:upload-shape: table
CREATE TABLE uploads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL
);
-- COUPLED:upload-shape:END
