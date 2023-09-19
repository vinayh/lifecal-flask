DROP TABLE IF EXISTS entries;

CREATE TABLE entries
(
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER   NOT NULL,
    created  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start    DATE      NOT NULL,
    category INTEGER   NOT NULL,
    note     TEXT
);

DROP TABLE IF EXISTS users;

CREATE TABLE users
(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    oauth_id   TEXT      NOT NULL,
    birth      DATE      NOT NULL,
    exp_years  INTEGER   NOT NULL,
    categories TEXT,
    email      TEXT
);