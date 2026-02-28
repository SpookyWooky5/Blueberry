-- 1) Clients table for tenant isolation
CREATE TABLE clients (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         VARCHAR(255)    NOT NULL,
  email        VARCHAR(255)    UNIQUE NOT NULL
);

-- 2) Raw emails, tagged by client
CREATE TABLE emails (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id      INTEGER        NOT NULL REFERENCES clients(id),
  message_id     VARCHAR(255)   NOT NULL,
  to_addr        VARCHAR(255)   NOT NULL,
  to_name        VARCHAR(255),
  from_addr      VARCHAR(255)   NOT NULL,
  from_name      VARCHAR(255),
  subject        VARCHAR(255),
  body           TEXT,
  time_received  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  child_of       VARCHAR(255),       -- e.g. parent message_id
  references     TEXT,               -- For threading
  responded      BOOLEAN        NOT NULL DEFAULT 0,
  FOREIGN KEY(child_of) REFERENCES emails(message_id)
);

-- 3) Precomputed embeddings for each email
CREATE TABLE email_embeddings (
  email_id     INTEGER     NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  client_id    INTEGER     NOT NULL REFERENCES clients(id),
  model        VARCHAR(100) NOT NULL,
  embedding    BLOB        NOT NULL,   -- serialize e.g. Float32 array
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (email_id, model)
);

-- 4) Hierarchical “memory” summaries
CREATE TABLE memories (
  id           INTEGER     PRIMARY KEY AUTOINCREMENT,
  client_id    INTEGER     NOT NULL REFERENCES clients(id),
  memory_type  VARCHAR(20) NOT NULL,        -- e.g. 'daily','weekly','monthly'
  period_start DATE        NOT NULL,        -- start of the interval
  period_end   DATE        NOT NULL,        -- end of the interval
  text         TEXT        NOT NULL,        -- LLM‐generated summary
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5) Embeddings for each memory summary
CREATE TABLE memory_embeddings (
  memory_id   INTEGER      NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  client_id   INTEGER      NOT NULL REFERENCES clients(id),
  model       VARCHAR(100) NOT NULL,
  embedding   BLOB         NOT NULL,
  PRIMARY KEY (memory_id, model)
);

-- 6) Link which raw emails contributed to each memory (optional)
CREATE TABLE memory_membership (
  memory_id  INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  email_id   INTEGER NOT NULL REFERENCES emails(id)  ON DELETE CASCADE,
  client_id  INTEGER NOT NULL REFERENCES clients(id),
  PRIMARY KEY (memory_id, email_id)
);

-- 7) Changes in Obsidian notes
CREATE TABLE obsidian_changes_history (
  id               INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
  message_id       VARCHAR(255),                     -- Mail or conversation thread, optional
  email_id         INTEGER     REFERENCES emails(id),-- Explicit link to an email, if applicable
  context          TEXT,                             -- Input context from conversation
  applied_change   TEXT,                             -- What the bot actually did
  file_modified    VARCHAR(512),                     -- Obsidian vault file path
  change_type      VARCHAR(50),                      -- e.g. 'append', 'replace', 'delete', etc.
  created_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 8) Vault file index with embeddings (Phase 2+)
CREATE TABLE vault_index (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path    VARCHAR(512) UNIQUE NOT NULL,   -- relative to VAULT_DIR
  file_type    VARCHAR(50)  NOT NULL,          -- 'daily','weekly','monthly','quarterly','goal'
  client_id    INTEGER REFERENCES clients(id),
  model        VARCHAR(100) NOT NULL,
  embedding    BLOB         NOT NULL,
  period_start DATE,                           -- non-null for memory files
  period_end   DATE,                           -- non-null for memory files
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 9) Explicitly tracked client goals
CREATE TABLE client_goals (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id       INTEGER NOT NULL REFERENCES clients(id),
  goal_text       TEXT NOT NULL,
  source_email_id INTEGER REFERENCES emails(id),
  status          VARCHAR(50) NOT NULL DEFAULT 'active', -- 'active','reminded_1'..'reminded_5','ignored','completed','failed','paused'
  deadline        DATE,                                  -- optional target date
  last_reminded   DATE,                                  -- date of last reminder email
  reminder_count  INTEGER NOT NULL DEFAULT 0,            -- 0..5, then auto-ignored
  habit_slug      VARCHAR(100),                          -- slug of parent Habits/ file
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(client_id, goal_text)
);
