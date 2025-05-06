CREATE TABLE emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,                        -- Unique ID for each mail
  message_id VARCHAR(255) NOT NULL,             -- Identifier for the mail thread
  to_addr VARCHAR(255) NOT NULL,
  to_name VARCHAR(255),
  from_addr VARCHAR(255) NOT NULL,
  from_name VARCHAR(255),
  subject VARCHAR(255),
  body TEXT,
  time_recevied TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  child_of VARCHAR(255),                             -- References id of a parent mail in the thread (nullable)
  CONSTRAINT fk_child FOREIGN KEY (child_of) REFERENCES emails(message_id)
);


CREATE TABLE summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
  message_id VARCHAR(255) NOT NULL,             -- Should correspond to emails.message_id
  to_addr VARCHAR(255) NOT NULL,
  to_name VARCHAR(255),
  from_addr VARCHAR(255) NOT NULL,
  from_name VARCHAR(255),
  subject VARCHAR(255),
  text_body_input TEXT,                         -- Original mail content
  text_body_output TEXT,                        -- LLM-generated response/action items
  summary TEXT,                                 -- Brief summary for quick review
  mood TEXT,
  thoughts TEXT,
  gratitutes TEXT,
  date_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_summary_message FOREIGN KEY (message_id) REFERENCES emails(message_id)
);


CREATE TABLE obsidian_changes_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
  message_id VARCHAR(255),                      -- Reference to mail or conversation thread (optional)
  context TEXT,                                 -- Context from the conversation (e.g., email or chat excerpt)
  requested_change TEXT,                        -- What you asked the bot to add/change
  applied_change TEXT,                          -- What was actually added/changed
  file_modified VARCHAR(512),                   -- File path in the Obsidian vault that was modified
  date_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX idx_emails_message_id ON emails(message_id);
CREATE INDEX idx_summaries_message_id ON summaries(message_id);
CREATE INDEX idx_obs_changes_message_id ON obsidian_changes_history(message_id);