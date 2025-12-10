"""MongoDB storage for conversation state persistence."""

from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from agentic.models import ConversationState


class MongoStore:
    """Handles persistence of conversation state to MongoDB."""

    def __init__(self, connection_string: str, database: str = "agentic_bot"):
        """
        Initialize MongoDB connection.

        Args:
            connection_string: MongoDB connection URI
            database: Database name to use
        """
        self.client: MongoClient = MongoClient(connection_string)
        self.db: Database = self.client[database]
        self.conversations: Collection = self.db["conversations"]

    def create_conversation(self, state: ConversationState) -> str:
        """
        Create a new conversation record.

        Args:
            state: The ConversationState to persist

        Returns:
            The conversation ID
        """
        doc = state.model_dump(mode="json")
        self.conversations.insert_one(doc)
        return state.id

    def update_conversation(self, conversation_id: str, updates: dict) -> None:
        """
        Update specific fields of a conversation.

        Args:
            conversation_id: The conversation ID to update
            updates: Dictionary of fields to update
        """
        self.conversations.update_one(
            {"id": conversation_id},
            {"$set": updates}
        )

    def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Retrieve a conversation by ID.

        Args:
            conversation_id: The conversation ID to retrieve

        Returns:
            The ConversationState if found, None otherwise
        """
        doc = self.conversations.find_one({"id": conversation_id})
        if doc is None:
            return None
        # Remove MongoDB's _id field before validation
        doc.pop("_id", None)
        return ConversationState.model_validate(doc)

    def get_user_conversations(
        self, user_id: int, limit: int = 10
    ) -> list[ConversationState]:
        """
        Get recent conversations for a user.

        Args:
            user_id: The Telegram user ID
            limit: Maximum number of conversations to return

        Returns:
            List of ConversationState objects, most recent first
        """
        cursor = (
            self.conversations.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        results = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(ConversationState.model_validate(doc))
        return results
