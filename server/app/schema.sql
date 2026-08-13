CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    pipeline_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    counts JSONB,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
