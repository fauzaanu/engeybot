"""Status message management for Telegram with auto-delete functionality."""

from typing import Optional
from huey import RedisHuey

from agentic.models import ProcessingStage, SourceInfo

# Auto-delete duration in seconds (24 hours)
AUTO_DELETE_DURATION = 86400

# Stage display messages in Dhivehi (no emojis)
STAGE_MESSAGES = {
    ProcessingStage.THINKING: "ވިސްނަނީ...",
    ProcessingStage.AWAITING_CLARIFICATION: "ސާފުކުރަން ބޭނުން...",
    ProcessingStage.DECOMPOSING: "ސުވާލު ދިރާސާކުރަނީ...",
    ProcessingStage.RESEARCHING: "ހޯދަނީ",
    ProcessingStage.SYNTHESIZING: "ޖަވާބު ތައްޔާރުކުރަނީ...",
    ProcessingStage.COMPLETE: "ނިމިއްޖެ",
    ProcessingStage.FAILED: "މައްސަލައެއް ދިމާވެއްޖެ",
}


def format_sources_html(sources: list[SourceInfo]) -> str:
    """Format a list of sources as HTML hyperlinks for Telegram display.
    
    Args:
        sources: List of SourceInfo objects with title and URL
        
    Returns:
        HTML string with sources as hyperlinks, separated by " | "
    """
    if not sources:
        return ""
    return " | ".join(source.to_html() for source in sources)


class StatusManager:
    """Manages status messages in Telegram with auto-delete functionality.
    
    This class handles sending and updating status messages during agentic
    processing, and schedules automatic deletion after 24 hours using Huey.
    """
    
    def __init__(self, bot, huey: Optional[RedisHuey] = None):
        """Initialize StatusManager.
        
        Args:
            bot: TeleBot instance for sending messages
            huey: Optional RedisHuey instance for scheduling deletions.
                  If not provided, auto-delete scheduling is disabled.
        """
        self.bot = bot
        self.huey = huey
        self._delete_task = None
        
        # Register the delete task if huey is provided
        if self.huey:
            self._register_delete_task()
    
    def _register_delete_task(self) -> None:
        """Register the delete message task with Huey."""
        @self.huey.task()
        def delete_message_task(chat_id: int, message_id: int):
            """Huey task to delete a message after delay."""
            try:
                self.bot.delete_message(chat_id, message_id)
            except Exception:
                # Message may already be deleted or chat may be unavailable
                pass
        
        self._delete_task = delete_message_task
    
    def _schedule_deletion(self, chat_id: int, message_id: int) -> None:
        """Schedule a message for deletion after AUTO_DELETE_DURATION seconds.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to delete
        """
        if self._delete_task:
            self._delete_task.schedule((chat_id, message_id), delay=AUTO_DELETE_DURATION)
    
    def send_initial_status(self, chat_id: int, reply_to: int) -> int:
        """Send initial 'Thinking...' message with auto-delete timer.
        
        Args:
            chat_id: Telegram chat ID
            reply_to: Message ID to reply to
            
        Returns:
            Message ID of the sent status message
        """
        message = self.bot.send_message(
            chat_id,
            STAGE_MESSAGES[ProcessingStage.THINKING],
            reply_to_message_id=reply_to,
            disable_web_page_preview=True,
        )
        self._schedule_deletion(chat_id, message.message_id)
        return message.message_id
    
    def update_status(
        self,
        chat_id: int,
        message_id: int,
        stage: ProcessingStage,
        progress: str = ""
    ) -> None:
        """Update status message with current stage and progress.
        
        The auto-delete timer is preserved from the original message.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Status message ID to update
            stage: Current processing stage
            progress: Optional progress string (e.g., "2/4")
        """
        text = STAGE_MESSAGES.get(stage, str(stage))
        if progress:
            text = f"{text} {progress}"
        
        try:
            self.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                disable_web_page_preview=True,
            )
        except Exception:
            # Message may have been deleted or is unchanged
            pass
    
    def replace_with_response(
        self,
        chat_id: int,
        message_id: int,
        response: str,
        parse_mode: Optional[str] = None
    ) -> None:
        """Replace status message with final response.
        
        The auto-delete timer is preserved from the original message.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Status message ID to replace
            response: Final response text
            parse_mode: Optional parse mode (e.g., "HTML", "Markdown")
        """
        try:
            self.bot.edit_message_text(
                response,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
        except Exception:
            # Message may have been deleted; send a new one
            new_message = self.bot.send_message(
                chat_id,
                response,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            self._schedule_deletion(chat_id, new_message.message_id)
    
    def send_with_auto_delete(
        self,
        chat_id: int,
        text: str,
        reply_to: Optional[int] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """Send a message configured to auto-delete after 24 hours.
        
        Args:
            chat_id: Telegram chat ID
            text: Message text to send
            reply_to: Optional message ID to reply to
            parse_mode: Optional parse mode (e.g., "HTML", "Markdown")
            
        Returns:
            Message ID of the sent message
        """
        message = self.bot.send_message(
            chat_id,
            text,
            reply_to_message_id=reply_to,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
        self._schedule_deletion(chat_id, message.message_id)
        return message.message_id


def get_stage_message(stage: ProcessingStage, progress: str = "") -> str:
    """Get the display message for a processing stage.
    
    Args:
        stage: The processing stage
        progress: Optional progress string
        
    Returns:
        The formatted stage message
    """
    text = STAGE_MESSAGES.get(stage, str(stage))
    if progress:
        text = f"{text} {progress}"
    return text
