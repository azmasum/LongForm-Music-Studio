-- LFMS database schema v1
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    duration_sec REAL NOT NULL DEFAULT 1800,
    bpm REAL NOT NULL DEFAULT 80,
    key_root TEXT NOT NULL DEFAULT 'C',
    key_mode TEXT NOT NULL DEFAULT 'MINOR',
    intensity REAL NOT NULL DEFAULT 50,
    genre TEXT NOT NULL DEFAULT 'AMBIENT',
    moods_json TEXT NOT NULL DEFAULT '["CALM"]',
    energy_curve TEXT NOT NULL DEFAULT 'FLAT',
    voiceover_safe INTEGER NOT NULL DEFAULT 0,
    ducking_amount REAL NOT NULL DEFAULT 60,
    speech_headroom_db REAL NOT NULL DEFAULT -12,
    seed INTEGER NOT NULL,
    generator_version TEXT NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    license_class TEXT NOT NULL DEFAULT 'ORIGINAL',
    fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'GENERATED',
    position INTEGER NOT NULL DEFAULT 0,
    volume_db REAL NOT NULL DEFAULT 0,
    pan REAL NOT NULL DEFAULT 0,
    mute INTEGER NOT NULL DEFAULT 0,
    solo INTEGER NOT NULL DEFAULT 0,
    effects_json TEXT NOT NULL DEFAULT '[]',
    automation_json TEXT NOT NULL DEFAULT '{}',
    source_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
    start_sec REAL NOT NULL DEFAULT 0,
    offset_sec REAL NOT NULL DEFAULT 0,
    duration_sec REAL,
    fade_in_sec REAL NOT NULL DEFAULT 0,
    fade_out_sec REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tracks_project ON tracks(project_id);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    duration_sec REAL,
    sample_rate INTEGER,
    channels INTEGER,
    license_class TEXT NOT NULL DEFAULT 'UNKNOWN',
    source TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    attribution_url TEXT NOT NULL DEFAULT '',
    commercial_use INTEGER,
    attribution_required INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    fingerprint TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS library_tracks (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    file_path TEXT NOT NULL,
    title TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'WAV',
    duration_sec REAL NOT NULL DEFAULT 0,
    bpm REAL,
    key_root TEXT,
    key_mode TEXT,
    genre TEXT NOT NULL DEFAULT '',
    moods_json TEXT NOT NULL DEFAULT '[]',
    intensity REAL,
    seed INTEGER,
    generator_version TEXT,
    license_class TEXT NOT NULL DEFAULT 'ORIGINAL',
    fingerprint TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    favorite INTEGER NOT NULL DEFAULT 0,
    collection TEXT NOT NULL DEFAULT '',
    rating INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    render_job_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_library_created ON library_tracks(created_at DESC);

CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(category, name)
);

CREATE TABLE IF NOT EXISTS render_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    output_path TEXT NOT NULL,
    container TEXT NOT NULL DEFAULT 'WAV',
    bit_depth INTEGER NOT NULL DEFAULT 24,
    bitrate_kbps INTEGER,
    sample_rate INTEGER NOT NULL DEFAULT 48000,
    channels INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'PENDING',
    progress REAL NOT NULL DEFAULT 0,
    error_text TEXT NOT NULL DEFAULT '',
    queued_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_render_status ON render_jobs(status);

CREATE TABLE IF NOT EXISTS provenance_records (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    certificate_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_provenance_subject ON provenance_records(subject_type, subject_id);

CREATE TABLE IF NOT EXISTS project_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    snapshot_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_versions_project ON project_versions(project_id, version_no DESC);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
