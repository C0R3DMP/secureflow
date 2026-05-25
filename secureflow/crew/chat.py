"""
Inter-agent communication system.
Allows agents to send messages and ask questions of each other.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from secureflow.crew.memory import SharedContext


class AgentMessage:
    """Represents a message sent between agents."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        requires_response: bool = False,
        timestamp: Optional[str] = None,
    ):
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.message = message
        self.requires_response = requires_response
        self.timestamp = timestamp or datetime.now().isoformat()
        self.response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "message": self.message,
            "requires_response": self.requires_response,
            "timestamp": self.timestamp,
            "response": self.response,
        }

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.from_agent} → {self.to_agent}: {self.message}"


class AgentCommunicator:
    """Manages communication between agents."""

    def __init__(self, context: SharedContext):
        self.context = context
        self.messages: List[AgentMessage] = []

    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        requires_response: bool = False,
    ) -> AgentMessage:
        """Send a message from one agent to another."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message=message,
            requires_response=requires_response,
        )
        self.messages.append(msg)
        self.context.log_message(from_agent, to_agent, message)
        print(f"📨 {msg}")
        return msg

    def broadcast_message(self, from_agent: str, message: str) -> AgentMessage:
        """Send a message to all agents."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent="all",
            message=message,
        )
        self.messages.append(msg)
        self.context.log_message(from_agent, "all", message)
        print(f"📢 {from_agent} → all: {message}")
        return msg

    def respond_to_message(self, original_msg: AgentMessage, response: str) -> None:
        """Respond to a message that required a response."""
        original_msg.response = response
        self.context.log_message(
            original_msg.to_agent,
            original_msg.from_agent,
            f"RE: {response}",
        )
        print(f"📝 {original_msg.to_agent} → {original_msg.from_agent}: {response}")

    def get_messages_for_agent(self, agent_name: str) -> List[AgentMessage]:
        """Get all messages directed at a specific agent."""
        return [
            msg
            for msg in self.messages
            if msg.to_agent == agent_name or msg.to_agent == "all"
        ]

    def get_messages_from_agent(self, agent_name: str) -> List[AgentMessage]:
        """Get all messages sent by a specific agent."""
        return [msg for msg in self.messages if msg.from_agent == agent_name]

    def get_conversation_between(
        self, agent1: str, agent2: str
    ) -> List[AgentMessage]:
        """Get conversation between two specific agents."""
        return [
            msg
            for msg in self.messages
            if (msg.from_agent == agent1 and msg.to_agent == agent2)
            or (msg.from_agent == agent2 and msg.to_agent == agent1)
        ]

    def has_pending_questions(self, agent_name: str) -> bool:
        """Check if agent has messages requiring response."""
        messages = self.get_messages_for_agent(agent_name)
        return any(msg.requires_response and not msg.response for msg in messages)

    def get_pending_questions(self, agent_name: str) -> List[AgentMessage]:
        """Get all pending questions for an agent."""
        messages = self.get_messages_for_agent(agent_name)
        return [msg for msg in messages if msg.requires_response and not msg.response]

    def export_chat_log(self) -> str:
        """Export full chat log as readable text."""
        log = "=== AGENT COMMUNICATION LOG ===\n\n"
        for msg in self.messages:
            log += f"{msg.timestamp}\n"
            log += f"  FROM: {msg.from_agent}\n"
            log += f"  TO: {msg.to_agent}\n"
            log += f"  MSG: {msg.message}\n"
            if msg.response:
                log += f"  RESPONSE: {msg.response}\n"
            log += "\n"
        return log
