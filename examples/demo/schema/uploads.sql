-- COUPLED:upload-shape: table
-- COUPLED:upload-columns: table /^([a-z_]+) /
CREATE TABLE uploads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'scanning', 'stored', 'rejected', 'expired'))  -- COUPLED:upload-status: table
);
-- COUPLED:upload-columns:END
-- COUPLED:upload-shape:END
