CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    pipeline_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    counts JSONB,
    error TEXT,
    definition_id UUID,
    graph_snapshot JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

-- Migrate pre-existing ``runs`` tables that predate the component-graph columns.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS definition_id UUID;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS graph_snapshot JSONB;

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, stage)
);

CREATE TABLE IF NOT EXISTS pipeline_definitions (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    graph JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS component_templates (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    component_id TEXT NOT NULL,
    variables JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
