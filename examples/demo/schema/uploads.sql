-- COUPLED:upload-shape: table
-- COUPLED:upload-columns: table
CREATE TABLE uploads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL
);
-- COUPLED:upload-columns:END
-- COUPLED:upload-shape:END
