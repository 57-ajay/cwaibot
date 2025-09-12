# models/state_model.py
"""Enhanced state management schema with error tracking for intelligent recovery"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage


class ConversationState(BaseModel):
    """Enhanced state for user's conversation with error tracking"""
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

    # Pagination
    current_page: int = 1

    # Error tracking for intelligent recovery
    error_count: int = 0
    last_error_type: Optional[str] = None
    failed_filter_combinations: List[Dict[str, Any]] = Field(default_factory=list)

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
            "error_count": self.error_count,
            "last_error_type": self.last_error_type,
            "failed_filter_combinations": self.failed_filter_combinations,
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
        self.driver_ids_notified = []
        self.current_page = 1
        self.error_count = 0
        self.last_error_type = None
        self.failed_filter_combinations = []

    def increment_error(self, error_type: str) -> None:
        """Track error occurrences for intelligent recovery"""
        if self.last_error_type == error_type:
            self.error_count += 1
        else:
            self.error_count = 1
            self.last_error_type = error_type

    def reset_error_tracking(self) -> None:
        """Reset error tracking after successful operation"""
        self.error_count = 0
        self.last_error_type = None

    def should_simplify_search(self) -> bool:
        """Determine if search should be simplified based on error count"""
        return self.error_count > 2

    def should_escalate_to_support(self) -> bool:
        """Determine if we should suggest support contact"""
        return self.error_count > 3
