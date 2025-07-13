# Project Blueberry

Project Blueberry is a sophisticated, AI-powered email assistant.

## Key Features

*   **Automated Email Processing:** Connects to a mail server (currently configured for Zoho) to automatically fetch new emails from predefined clients and send replies.
*   **LLM Integration:** Utilizes Large Language Models (LLMs) for advanced text processing:
    *   **Summarization:** Generates daily, weekly, monthly, and quarterly summaries of email conversations.
    *   **Natural Language Response:** Crafts context-aware, human-like replies to incoming emails.
    *   **Semantic Embeddings:** Creates vector embeddings of emails and summaries for deep semantic understanding and similarity-based context retrieval.
*   **Persistent Memory System:** Implements a hierarchical "memory" system by storing summaries and past interactions in a database. This provides the assistant with long-term context, enabling it to recall relevant information across different conversations.
*   **Database Backend:** Employs an SQLite database to manage all operational data, including:
    *   Raw email content
    *   Client information
    *   Embeddings for emails and memories
    *   Hierarchical memory summaries
*   **Task Automation:** Designed for autonomous operation using cron jobs to periodically fetch mail, generate responses, and create summaries.
*   **Obsidian Integration (Planned):** The database schema and project structure include plans for future integration with the Obsidian note-taking app, likely for logging actions or creating knowledge base entries from email content.

In short, **Project Blueberry is an intelligent agent that automates email management by understanding, summarizing, and responding to conversations using an LLM with a persistent, long-term memory.**