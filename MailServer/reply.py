# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 14-MAY-2025  Initial Draft
# 12-JUL-2025  Refactor for threading and context
# 28-FEB-2026  Add classification routing, goal injection, RAG fixes
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import email
import pickle
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import frontmatter as fm
import numpy as np

from Logging import logger_init
from LLM.parse import parse, remove_commands
from LLM.extract_goals import extract_and_save_goals
from LLM.extract_knowledge import extract_and_save_knowledge
from LLM.extract_patterns import extract_and_save_pattern
from LLM.classify import classify_email
from LLM import OllamaChat, OllamaEmbed, cosine
from Database import connect_to_dataset, get_or_create_client
from Obsidian import update_goal
from Obsidian.writer import _slugify
from utils import (
    remove_think_blocks,
    read_prompt_from_file,
    LLM_MODEL,
    EMB_MODEL,
    VAULT_DIR,
    EMAIL,
    PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    CLIENTS,
    CLIENTNAMES,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
SIMILARITY_THRESHOLD = 0.65

# ================================= FUNCTIONS ================================ #
def _handle_goal_acknowledgment(db, emb, client_id, email_text, context_parts):
    """Finds the best-matching active goal, resets its reminder state, injects context."""
    try:
        embedding = emb.embed(email_text, is_query=True)
        goal_rows = list(db['vault_index'].find(client_id=client_id, file_type='goals'))
        if not goal_rows or embedding is None:
            return

        best_sim, best_row = max(
            ((cosine(np.array(embedding), np.array(pickle.loads(r['embedding']))), r)
             for r in goal_rows),
            key=lambda x: x[0]
        )

        rel_path = best_row['file_path']
        abs_path = os.path.join(VAULT_DIR, rel_path)
        post = fm.load(abs_path)
        goal_text = post.content.strip()
        slug = _slugify(goal_text)

        update_goal(slug, reminder_count=0, status='active', last_reminded=None)
        db['client_goals'].update(
            dict(goal_text=goal_text, reminder_count=0, status='active', last_reminded=None),
            ['goal_text']
        )
        context_parts.append(f"[GOAL ACKNOWLEDGED: {goal_text}]")
        LOGGER.info(f"Goal acknowledged and reset: '{goal_text[:60]}'")
    except Exception as e:
        LOGGER.error(f"Could not handle goal acknowledgment: {e}")


def get_context_from_config(db, emb, client_id, current_email_text, config, labels=None):
    """Builds the context string based on the parsed command configuration."""
    if labels is None:
        labels = []
    context_parts = []
    seen_ids = set()

    # 0. Handle goal acknowledgment (resets reminder state, injects confirmation)
    if 'goal_acknowledge' in labels:
        _handle_goal_acknowledgment(db, emb, client_id, current_email_text, context_parts)

    # 0b. Flag ambiguous goal update so the LLM asks for clarification
    if 'goal_update_ambiguous' in labels:
        context_parts.append(
            "[NOTE: This email may contain a goal update. If so, include one focused clarifying question: "
            "'Were you updating me on [goal]?']"
        )

    # 1. Inject user profile (always, if file exists — small file, ~200 tokens)
    profile_path = os.path.join(VAULT_DIR, "Knowledge", "profile.md")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, encoding='utf-8') as f:
                profile_content = f.read().strip()
            if profile_content:
                context_parts.append(f"[USER PROFILE]\n{profile_content}")
        except Exception as e:
            LOGGER.error(f"Could not read profile.md: {e}")

    # 2. Always inject active goals
    try:
        active_goals = list(db['client_goals'].find(client_id=client_id, status='active'))
        if active_goals:
            goals_text = "\n".join(f"- {g['goal_text']}" for g in active_goals)
            context_parts.insert(0, f"[ACTIVE GOALS]\n{goals_text}")
    except Exception as e:
        LOGGER.error(f"Could not retrieve active goals: {e}")

    # 3. Handle time-based memories from /remember command
    if config.get("remember", {}).get("enable"):
        LOGGER.info("Retrieving recent memories based on time filters.")
        for period, limit in config["remember"]["time_filters"].items():
            if not limit:
                continue
            try:
                records = list(db['vault_index'].find(
                    client_id=client_id,
                    file_type=period,
                    order_by='-period_start',
                    _limit=limit
                ))
                for row in records:
                    if row['id'] not in seen_ids:
                        seen_ids.add(row['id'])
                        abs_path = os.path.join(VAULT_DIR, row['file_path'])
                        post = fm.load(abs_path)
                        context_parts.append(
                            f"[{period.upper()} SUMMARY from {row['period_start']}]\n"
                            f"{post.content}\n"
                        )
            except Exception as e:
                LOGGER.error(f"Could not find {period} memories: {e}")

    # 4. Handle similarity-based memories from /embeds command
    if config.get("embeds", {}).get("enable"):
        LOGGER.info("Retrieving relevant memories based on similarity.")
        top_k = config["embeds"].get("topk", 3)

        try:
            current_embedding = emb.embed(current_email_text, is_query=True)
            past = list(db['vault_index'].find(client_id=client_id))
            if past and current_embedding is not None:
                similarities = [
                    (cosine(np.array(current_embedding), np.array(pickle.loads(row['embedding']))),
                     row['id'], row['file_path'], row['period_start'])
                    for row in past
                ]
                similarities = [(s, i, p, d) for s, i, p, d in similarities if s >= SIMILARITY_THRESHOLD]
                similarities.sort(key=lambda x: x[0], reverse=True)
                for sim, row_id, rel_path, period_start in similarities[:top_k]:
                    if row_id not in seen_ids:
                        seen_ids.add(row_id)
                        abs_path = os.path.join(VAULT_DIR, rel_path)
                        post = fm.load(abs_path)
                        context_parts.append(
                            f"[PAST MEMORY from {period_start}]\n{post.content}\n[/PAST MEMORY]"
                        )
        except Exception as e:
            LOGGER.error(f"Could not retrieve relevant context by similarity: {e}")

    return "\n\n".join(context_parts)


def reply():
	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']

	# Init LLM
	llm = OllamaChat(LLM_MODEL)
	# Init Embedder
	emb = OllamaEmbed(EMB_MODEL)

	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue

		try:
			LOGGER.debug(f"Retrieving unreplied mails from DB for client {client_id}")
			unresponded = tuple(email_table.find(
				client_id=client_id,
				responded=0,
				order_by='id'
			))
		except Exception as e:
			LOGGER.error(f"Could not collect unreplied mails from DB, {e}")
			continue

		if not unresponded:
			continue

		LOGGER.info(f"Found {len(unresponded)} unreplied mails from client {client_id}")

		last_mail = unresponded[-1]

		# Classify the most recent email to route appropriately
		classification = classify_email(llm, last_mail['subject'], last_mail['body'])
		labels = classification.get("labels", ["casual"])
		LOGGER.info(f"Email classified as: {labels}, tags: {classification.get('tags', [])}")

		raw_email_body = "\n\n---\n\n".join(mail['body'] for mail in unresponded)
		context_config = parse(unresponded[-1]['body'])

		# Clean the body for the LLM
		cleaned_email_text = remove_commands(raw_email_body)
		cleaned_email_text = remove_think_blocks(cleaned_email_text)
		cleaned_email_text = cleaned_email_text.replace("/think", "")

		# Route: casual-only emails skip full RAG
		is_casual_only = labels == ["casual"] or labels == ["casual".strip()]
		if is_casual_only:
			LOGGER.info("Casual email detected — skipping deep RAG retrieval")
			context = ""
		else:
			context = get_context_from_config(db, emb, client_id, cleaned_email_text, context_config, labels)

		prompt_template = read_prompt_from_file("mail_prompt.txt")
		if not prompt_template:
			LOGGER.error("Failed to read mail prompt, skipping reply for this client.")
			continue

		final_prompt = prompt_template.format(
			context=context,
			client_name=client_name,
			current_email=cleaned_email_text
		)

		history = [{"role": "system", "content": final_prompt}]
		llm.init_history(history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue

		response_msg_id = email.utils.make_msgid()

		parent_message_id = last_mail['message_id']
		parent_references = last_mail.get('references') or ''

		ref_list = parent_references.split()
		if parent_message_id not in ref_list:
			ref_list.append(parent_message_id)
		new_references = " ".join(ref_list)

		# Add LLM response to DB
		db.begin()
		try:
			LOGGER.debug(f"Inserting response for thread '{last_mail['subject']}' into table 'emails'")
			email_id = email_table.insert(dict(
				client_id=client_id,
				message_id=response_msg_id,
				to_addr=last_mail['from_addr'],
				to_name=last_mail['from_name'],
				from_addr=last_mail['to_addr'],
				from_name=last_mail['to_name'],
				subject=last_mail['subject'],
				body=llm_output,
				child_of=parent_message_id,
				references=new_references,
				responded=1
			))
			embedding = emb.embed(f"Subject: {last_mail['subject']}\nBody: {llm_output}")
			email_embed_table.insert(dict(
				email_id=email_id,
				client_id=client_id,
				model=EMB_MODEL,
				embedding=pickle.dumps(embedding)
			))
			db.commit()
			LOGGER.debug("Inserted record in table 'emails'")
		except Exception as e:
			LOGGER.error(f"Could not insert mail into 'emails': {e}")
			db.rollback()
			continue

		# Reply to client
		response_mail = MIMEMultipart()
		response_mail["From"] = EMAIL
		response_mail["To"] = last_mail['from_addr']
		response_mail["Subject"] = last_mail['subject']
		response_mail["Message-ID"] = response_msg_id
		response_mail["In-Reply-To"] = parent_message_id
		response_mail["References"] = new_references
		response_mail.attach(MIMEText(llm_output, "plain"))

		LOGGER.debug("Response mail formatted. Sending...")
		try:
			with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
				smtp_server.login(EMAIL, PASSWORD)
				smtp_server.sendmail(EMAIL, last_mail['from_addr'], response_mail.as_string())
			LOGGER.info(f"Successfully sent reply to {last_mail['from_addr']}")
		except Exception as e:
			LOGGER.error(f"Error occurred while sending mail: {e}")
			continue

		# Mark unresponded mails as responded and extract goals
		try:
			ids_to_update = [mail['id'] for mail in unresponded]
			email_table.update_many([dict(id=id, responded=1) for id in ids_to_update], ['id'])
			LOGGER.debug(f"Marked {len(ids_to_update)} mails as responded")

			# --- Extract and Save Goals ---
			conversation_parts = []
			for mail in unresponded:
				if mail['from_addr'] == client:
					conversation_parts.append(f"User: {mail['body']}")
				else:
					conversation_parts.append(f"Assistant: {mail['body']}")

			conversation_for_goal_extraction = "\n\n".join(conversation_parts)
			extract_and_save_goals(client_id, conversation_for_goal_extraction, last_mail['id'])

			if 'knowledge' in labels:
				try:
					extract_and_save_knowledge(client_id, cleaned_email_text, last_mail['id'])
				except Exception as e:
					LOGGER.error(f"Knowledge extraction failed: {e}")

			if 'pattern' in labels:
				try:
					extract_and_save_pattern(client_id, cleaned_email_text)
				except Exception as e:
					LOGGER.error(f"Pattern extraction failed: {e}")
			# --- End Goal/Knowledge/Pattern Extraction ---

		except Exception as e:
			LOGGER.error(f"Could not mark mails as responded or extract goals: {e}")

# =================================== MAIN =================================== #
if __name__ == "__main__":
	reply()
