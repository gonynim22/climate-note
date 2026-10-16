CREATE TABLE app_settings (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL
                );
CREATE TABLE dday_widgets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    x_pos       INTEGER NOT NULL DEFAULT 100,
                    y_pos       INTEGER NOT NULL DEFAULT 100,
                    is_open     INTEGER NOT NULL DEFAULT 1,
                    color       TEXT DEFAULT '#D6EEFF'
                );
CREATE TABLE focus_sessions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    widget_id       INTEGER,
                    goal            TEXT NOT NULL DEFAULT '',
                    mode_key        TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes   INTEGER NOT NULL DEFAULT 25,
                    break_minutes   INTEGER NOT NULL DEFAULT 5,
                    started_at      TEXT NOT NULL,
                    ended_at        TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    completed       INTEGER NOT NULL DEFAULT 0,
                    focus_rating    INTEGER,
                    distraction     TEXT NOT NULL DEFAULT '없음',
                    created_at      TEXT NOT NULL
                );
CREATE TABLE focus_widgets (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal          TEXT NOT NULL DEFAULT '',
                    mode_key      TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes INTEGER NOT NULL DEFAULT 25,
                    break_minutes INTEGER NOT NULL DEFAULT 5,
                    x_pos         INTEGER NOT NULL DEFAULT 160,
                    y_pos         INTEGER NOT NULL DEFAULT 160,
                    is_open       INTEGER NOT NULL DEFAULT 1,
                    is_pinned     INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL
                );
CREATE TABLE memos (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
CREATE TABLE schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    color      TEXT DEFAULT '#FFD166'
                );
CREATE TABLE shortcuts (
                    id   INTEGER PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT ''
                );
CREATE TABLE sticky_notes (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    type      TEXT NOT NULL DEFAULT 'memo',
                    content   TEXT NOT NULL DEFAULT '',
                    x_pos     INTEGER NOT NULL DEFAULT 100,
                    y_pos     INTEGER NOT NULL DEFAULT 100,
                    width     INTEGER NOT NULL DEFAULT 300,
                    height    INTEGER NOT NULL DEFAULT 400,
                    is_open   INTEGER NOT NULL DEFAULT 1,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    color     TEXT DEFAULT '#FFFDD2'
                , is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT NOT NULL DEFAULT '');
INSERT INTO app_settings (key, value) VALUES ('app_font', 'Malgun Gothic');
INSERT INTO app_settings (key, value) VALUES ('app_opacity', '100');
INSERT INTO app_settings (key, value) VALUES ('calendar_position_mode', 'corner');
INSERT INTO app_settings (key, value) VALUES ('calendar_scale', 'compact');
INSERT INTO app_settings (key, value) VALUES ('desktop_mode', '0');
INSERT INTO app_settings (key, value) VALUES ('keep_on_show_desktop', '1');
INSERT INTO app_settings (key, value) VALUES ('privacy_pin', '0000');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_1', '#FFD166');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_2', '#4CC9F0');
INSERT INTO app_settings (key, value) VALUES ('schedule_color_3', '#FF6B6B');
INSERT INTO app_settings (key, value) VALUES ('show_law_search', '1');
INSERT INTO app_settings (key, value) VALUES ('show_sidebar', '0');
INSERT INTO shortcuts (id, name, path) VALUES (1, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (2, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (3, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (4, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (5, '', '');
INSERT INTO shortcuts (id, name, path) VALUES (6, '', '');
