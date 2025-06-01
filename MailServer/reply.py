# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 14-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import email
import pickle
import smtplib
from datetime import timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import numpy as np
from dotenv import load_dotenv

from Logging import logger_init
from LLM.parse import parse, remove_commands
from LLM import BaseChatbot, BaseEmbedder, cosine
from Database import connect_to_dataset, get_or_create_client
from utils import load_config, load_secrets, read_file_from_cfg, remove_think_blocks

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))

LLMCFG = load_config()["LLM"]

secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
SMTP_HOST = secrets["Mail"]["Zoho"]["smtp"]["host"]
SMTP_PORT = secrets["Mail"]["Zoho"]["smtp"]["port"]
CLIENTS   = secrets["Mail"]["Clients"]
CLIENTNAMES = secrets["Mail"]["ClientNames"]
del secrets

LLM_MODEL = os.getenv("LLM_MODEL")
EMB_MODEL = os.getenv("EMB_MODEL")

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def get_history(unresponded):
	LOGGER.debug("Collecting history")
	
	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']
	memory_table = db['memories']
	memory_embed_table = db['memory_embeddings']

	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	client_id = unresponded[0]['client_id']
	first_mail_date = unresponded[0]['time_received'].replace(hour=0, minute=0, second=0, microsecond=0)
	last_mail_date  = unresponded[-1]['time_received'].replace(hour=0, minute=0, second=0, microsecond=0)

	history = [
		{"role": "system", "content": read_file_from_cfg(os.path.join("prompts", "mail_prompt.txt"))},
	]

	unresponded_body = "\n\n".join(mail['body'] for mail in unresponded)
	context_config = parse(unresponded_body)
	unresponded_body = remove_commands(remove_think_blocks(unresponded_body))

	unresponded_body.replace("/think", "")
	if "/think" in unresponded[-1]["body"]:
		unresponded_body += "\n/think"
	else:
		unresponded_body += "\n/nothink"

	if context_config["remember"]["enable"]:
		content = temp = 'Refer to below summaries of the user\'s past interactions to generate an appropriate response:\n'
		
		LOGGER.info("Applying filters to retrieve recent memories")
		for k, v in context_config["remember"]["time_filters"].items():
			if not v:
				continue
			try:
				data = tuple(memory_table.find(
					client_id = client_id,
					memory_type = k,
					order_by  = '-id',
					_limit = v
				))
				LOGGER.debug(f"Found {len(data)} {k} memories")
				
				for row in data:
					content += f'\n{row["memory_type"]} summary from {row["period_start"]} to {row["period_end"]}'
					content += '\n--- BEGIN SUMMARY ---'
					content += f'\n{row["text"]}'
					content += '\n--- END SUMMARY ---'

			except Exception as e:
				LOGGER.error(f"Could not find {k} memories, {e}")
				continue
		
		if content != temp:
			history.append(
				{"role": "system", "content": content}
			)

		if context_config["remember"]["today_emails"]:
			try:
				data = email_table.find(
					client_id = client_id,
					responded = 1,
					time_received = {
						'gt': first_mail_date,
						'lt': last_mail_date + timedelta(days=1)
					},
					order_by  = 'id'
				)
			except Exception as e:
				LOGGER.error(f"Could not find today's mails, {e}")
			
			for i, row in enumerate(data):
				content = f'Datetime: {row["time_received"]}\nSubject: {row["subject"]}\nBody:\n{row["body"]}\nFrom: {row["from_name"]}'
				
				# Dont think by default
				content.replace("/think", "")
				if "/think" not in content:
					content += "\n/nothink"
				
				if row["to_addr"] != EMAIL:
					history.append(
						{"role": "assistant", "content": content}
					)
				else:
					history.append(
						{"role": "user", "content": remove_commands(content)}
					)
	
	if context_config["embeds"]["enable"]:
		content = f'Below are the Top {context_config["embeds"]["topk"]} previous mails and memories relevant to this conversation:\n'

		try:
			LOGGER.debug("Embedding unreplied mails")
			query_emb = emb.embed("", unresponded_body)

			LOGGER.debug("Finding related emails and memories")
			eml_embds = email_embed_table.find(
				client_id = client_id,
				email_id = {
					'notin': [mail['id'] for mail in unresponded]
				}
			)
			mem_embds = memory_embed_table.find(client_id=client_id)

			LOGGER.debug("Computing cosine similarites")
			eml_sims = [(me["email_id"], 'email', cosine(query_emb, pickle.loads(me["embedding"]))) for me in eml_embds]
			mem_sims = eml_sims.extend([(me["memory_id"], 'memory', cosine(query_emb, pickle.loads(me["embedding"]))) for me in mem_embds])
			top_sim_ids = [(meid, metype) for (meid, metype, _) in sorted(mem_sims, key=lambda x:-x[2])[:context_config["embeds"]["topk"]]]

			relevant_mails = email_table.find(
				client_id = client_id,
				id = [meid for (meid, metype, _) in top_sim_ids if metype == 'email']
			)
			for mail in relevant_mails:
				content += f'Mail:\nSubject: {mail["subject"]}\nBody: {mail["body"]}\n'
			
			relevant_memories = memory_table.find(
				client_id = client_id,
				id = [meid for (meid, metype, _) in top_sim_ids if metype == 'memory']
			)
			for memo in relevant_memories:
				content += f'Memory from {memo["created_at"]}: {memo["text"]}\n'
			
			LOGGER.debug("Computation complete. Adding data to history")
			history = [
				{"role": "system", "content": content},
			]
		except Exception as e:
			LOGGER.error(f"Could not compute cosine similarities, {e}")

	history.append(
		{"role": "user", "content": unresponded_body}
	)
	return history

def reply():
	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']

	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)
	
	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue
		
		#  Get unreplied emails from DB
		try:
			LOGGER.debug(f"Retrieving unreplied mails from DB")
			unresponded = tuple(email_table.find(
				client_id = client_id,
				responded = 0,
				order_by  = 'id'
			))
		except Exception as e:
			LOGGER.error(f"Could not collect unreplied mails from DB, {e}")
		
		LOGGER.info(f"Found {len(unresponded)} unreplied mails from client {client_id}")
		if len(unresponded) == 0:
			continue
		
		# Call LLM for response
		history = get_history(unresponded)
		llm.init_history('mail', history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue

		response_msg_id = email.utils.make_msgid()

		last_mail = unresponded[-1]

		# Add LLM response to DB
		db.begin()
		try:
			LOGGER.debug(f"Inserting response of {last_mail['message_id']} into table 'emails'")

			email_id = email_table.insert(dict(
				client_id = client_id,
				message_id = response_msg_id,
				to_addr = last_mail['from_addr'],
				to_name = last_mail['from_name'],
				from_addr = last_mail['to_addr'],
				from_name = last_mail['to_name'],
				subject = last_mail['subject'],
				body = llm_output,
				child_of = last_mail['message_id'],
				responded = 1
			))
			embedding = emb.embed(last_mail['subject'], llm_output)
			email_embed_table.insert(dict(
				email_id = email_id,
				client_id = client_id,
				model = EMB_MODEL,
				embedding = pickle.dumps(embedding)
			))
			db.commit()

			LOGGER.debug("Inserted record in table 'emails'")
		except Exception as e:
			LOGGER.error(f"Could not insert mail {last_mail['message_id']} in table 'emails': {e}")
			db.rollback()


		# Reply output to client
		for mail in unresponded:
			references = mail.get("References", "")
			parent_refs = [
				ref.strip() for ref in references.split() 
				if ref.strip().startswith("<") and ref.strip().endswith(">")
			]
			if mail['message_id'] not in parent_refs:
				parent_refs.append(mail['message_id'])

		response_mail = MIMEMultipart()
		response_mail["From"] = EMAIL
		response_mail["To"] = last_mail['from_addr']
		response_mail["Subject"] = last_mail['subject']
		response_mail["Message-ID"] = response_msg_id
		response_mail["In-Reply-To"] = mail['message_id']
		response_mail["References"] = " ".join(parent_refs)

		response_mail.attach(
			MIMEText(llm_output, "plain")
		)
		LOGGER.debug("Response mail formatted")

		try:
			LOGGER.debug("Sending mail to client...")
			with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
				smtp_server.login(EMAIL, PASSWORD)
				smtp_server.sendmail(EMAIL, last_mail['from_addr'], response_mail.as_string())
		except Exception as e:
			LOGGER.error(f"Error occured while sending mail, {e}")
			continue
		
		# Mark unresponded mails as responded
		try:
			LOGGER.debug(f"Marking {len(unresponded)} mails as responded")
			email_table.update_many(
				[dict(id = mail['id'], responded=1) for mail in unresponded],
				['id']
			)
		except Exception as e:
			LOGGER.error(f"Could not mark mails as responded, {e}")
			

# =================================== MAIN =================================== #
if __name__ == "__main__":
	reply()