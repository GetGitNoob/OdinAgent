"""ODIN Agent - Context Management.

Baut die LLM-Nachrichten aus System-Prompt + Conversation-Historie.
Kuemmert sich um History-Limits (MAX_HISTORY_MESSAGES) und bereitet
spaeter summarization / pruning / tool-compression vor.

Conversation Storage ist VOLLSTAENDIG getrennt (conversation.py).
"""
from __future__ import annotations

from config import Config


class AgentContext:
    def __init__(self, config: Config) -> None:
        self.config = config

    def build_messages(
        self,
        history: list[dict],
        *,
        system_override: str | None = None,
    ) -> list[dict]:
        """Baut die LLM-Message-Liste fuer einen Completion-Call.

        history = [{"role":..., "content":...}, ...] (bereits gekuerzt)
        """
        messages = [
            {"role": "system", "content": system_override or self.config.system_prompt}
        ]
        # Speichern: nur die letzten MAX_HISTORY_MESSAGES
        trimmed = history[-self.config.max_history_messages :]
        messages.extend(trimmed)
        return messages

    @staticmethod
    def trim(history: list[dict], max_messages: int) -> list[dict]:
        """Kuerzt die Historie auf die letzten max_messages (einfach)."""
        if len(history) <= max_messages:
            return history
        return history[-max_messages:]