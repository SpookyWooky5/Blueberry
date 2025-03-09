DROP TABLE IF EXISTS emails;
DROP TABLE IF EXISTS summaries;
DROP TABLE IF EXISTS obsidian_changes_history;

DROP INDEX IF EXISTS idx_emails_message_id;
DROP INDEX IF EXISTS idx_summaries_message_id;
DROP INDEX IF EXISTS idx_obs_changes_message_id;