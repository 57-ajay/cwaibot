# models/state_model.py
"""Minimal state management schema for cab booking flow"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage


class ConversationState(BaseModel):
    """Minimal state for user's conversation - only essentials"""
    model_config = {"arbitrary_types_allowed": True}

    # Chat history
    chat_history: List[BaseMessage] = Field(default_factory=list)

    # Applied filters/preferences
    applied_filters: Dict[str, Any] = Field(default_factory=dict)

    # Trip details
    trip_id: Optional[str] = None
    pickup_location: Optional[str] = None
    drop_location: Optional[str] = None
    trip_type: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM-DD format
    end_date: Optional[str] = None    # YYYY-MM-DD format

    # Customer details
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_profile: Optional[str] = None

    # Agent state
    last_bot_response: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)

    # Booking status - only keep driver IDs
    booking_status: Optional[str] = None
    driver_ids_notified: List[str] = Field(default_factory=list)

    current_page: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for graph state"""
        return {
            "chat_history": self.chat_history,
            "applied_filters": self.applied_filters,
            "trip_id": self.trip_id,
            "pickup_location": self.pickup_location,
            "drop_location": self.drop_location,
            "trip_type": self.trip_type,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_profile": self.customer_profile,
            "last_bot_response": self.last_bot_response,
            "tool_calls": self.tool_calls,
            "booking_status": self.booking_status,
            "driver_ids_notified": self.driver_ids_notified,
            "current_page": self.current_page,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        """Create from dictionary"""
        return cls(**data)

    def reset(self) -> None:
        """Reset the conversation state"""
        self.chat_history = []
        self.applied_filters = {}
        self.trip_id = None
        self.pickup_location = None
        self.drop_location = None
        self.trip_type = None
        self.start_date = None
        self.end_date = None
        self.last_bot_response = None
        self.tool_calls = []
        self.booking_status = None
        self.driver_ids_notified = [],
        self.current_page = 1
