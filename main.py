# main.py
"""Clean and optimized main application for cab booking bot"""

import os
import asyncio
from typing import Any, Optional, Dict
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

# Import agent and state model
from langgraph_agent.graph.builder import app as cab_agent
from models.state_model import ConversationState
from services.redis_service import redis_manager

# Minimal logging setup
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# Lifecycle management for Redis
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - initialize and cleanup Redis"""
    # Startup
    await redis_manager.initialize()

    # Check Redis health
    health = await redis_manager.health_check()
    if health.get("redis_available"):
        logger.info(f"Redis connected: {health.get('status')}")
    else:
        logger.warning("Redis not available - using fallback storage")

    yield

    # Shutdown
    await redis_manager.close()


# Initialize FastAPI with lifespan
app = FastAPI(title="Cab Booking Bot", lifespan=lifespan)

# CORS configuration
origins = [
    "https://www.cabswale.ai",
    "http://localhost:3000",
    "https://cabswale-landing-page-dev--cabswale-ai.us-central1.hosted.app",
    "https://cabswale-ai.web.app",
    "https://us-central1-cabswale-ai.cloudfunctions.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fallback in-memory storage for when Redis is unavailable
fallback_storage: Dict[str, ConversationState] = {}


# Request model for the /chat endpoint
class ChatRequest(BaseModel):
    user_id: str
    message: str
    customer_id: Optional[str] = ""
    customer_name: Optional[str] = ""
    customer_profile: Optional[str] = ""
    customer_phone: Optional[str] = ""
    source: Optional[str] = "app"
    pickupLocation: Optional[Dict[str, Any]] = None
    dropLocation: Optional[Dict[str, Any]] = None


async def get_user_state(
    user_id: str,
    customer_details: dict = None,
    source: str = "app",
    location_objects: dict = None
) -> ConversationState:
    """Get or create user conversation state"""

    # Try to get from Redis first
    state = await redis_manager.get_session(user_id)

    if state:
        # Update customer details and source if provided
        if customer_details:
            updated = False
            for key in ["customer_id", "customer_name", "customer_phone", "customer_profile"]:
                if customer_details.get(key) and getattr(state, key) != customer_details[key]:
                    setattr(state, key, customer_details[key])
                    updated = True

            if source and state.source != source:
                state.source = source
                updated = True

            # Update location objects if provided
            if location_objects:
                if location_objects.get("pickupLocation"):
                    state.pickup_location_object = location_objects["pickupLocation"]
                    updated = True
                if location_objects.get("dropLocation"):
                    state.drop_location_object = location_objects["dropLocation"]
                    updated = True

            if updated:
                await redis_manager.save_session(user_id, state)

        return state

    # Check fallback storage
    if user_id in fallback_storage:
        # Update source and locations if provided
        if source:
            fallback_storage[user_id].source = source
        if location_objects:
            if location_objects.get("pickupLocation"):
                fallback_storage[user_id].pickup_location_object = location_objects["pickupLocation"]
            if location_objects.get("dropLocation"):
                fallback_storage[user_id].drop_location_object = location_objects["dropLocation"]
        return fallback_storage[user_id]

    # Create new session
    new_state = ConversationState(
        chat_history=[],
        user_preferences={},
        trip_id=None,
        pickup_location=None,
        drop_location=None,
        pickup_location_object=location_objects.get("pickupLocation") if location_objects else None,
        drop_location_object=location_objects.get("dropLocation") if location_objects else None,
        trip_type=None,
        start_date=None,
        end_date=None,
        customer_id=customer_details.get("customer_id") if customer_details else None,
        customer_name=customer_details.get("customer_name") if customer_details else None,
        customer_phone=customer_details.get("customer_phone") if customer_details else None,
        customer_profile=customer_details.get("customer_profile") if customer_details else None,
        last_bot_response=None,
        tool_calls=[],
        booking_status=None,
        source=source,
        passenger_count=None
    )

    # Save to Redis or fallback
    if not await redis_manager.save_session(user_id, new_state):
        fallback_storage[user_id] = new_state

    return new_state


async def save_user_state(user_id: str, state: ConversationState) -> bool:
    """Save user state to Redis with fallback"""
    success = await redis_manager.save_session(user_id, state)

    if not success:
        fallback_storage[user_id] = state

    return success


async def clear_user_session(user_id: str) -> bool:
    """Clear user session from Redis and fallback storage"""
    redis_deleted = await redis_manager.delete_session(user_id)

    if user_id in fallback_storage:
        del fallback_storage[user_id]

    return redis_deleted


async def process_message_async(
    user_id: str,
    message: str,
    customer_details: dict = {},
    source: str = "app",
    location_objects: dict = {}
) -> str:
    """Process user message through cab agent"""

    # Get user state
    state_model = await get_user_state(user_id, customer_details, source, location_objects)

    # Handle reset command
    if message.lower().strip() in ["reset", "start over", "restart"]:
        await clear_user_session(user_id)
        return "🔄 Let's start fresh! Please tell me your pickup city, destination, travel date, and whether it's a one-way or round trip."

    # Check for explicit cancellation request
    cancel_keywords = [
        "cancel", "cancel trip", "cancel booking", "cancel my trip",
        "cancel the ride", "abort", "cancel my cab", "stop booking",
        "don't want the cab", "cancel the booking"
    ]

    message_lower = message.lower().strip()
    is_cancel_request = any(keyword in message_lower for keyword in cancel_keywords)

    if is_cancel_request and not state_model.trip_id:
        return "I don't see any active trip to cancel. Would you like to book a new cab?"

    # Add message to chat history
    state_model.chat_history.append(HumanMessage(content=message))

    # Convert Pydantic model to dict for the agent
    state_dict = state_model.to_dict()

    # Process through agent
    try:
        # Run the sync agent in a thread pool
        loop = asyncio.get_event_loop()

        result = await asyncio.wait_for(
            loop.run_in_executor(None, cab_agent.invoke, state_dict),
            timeout=30.0
        )

        if not isinstance(result, dict):
            logger.warning(f"Agent returned non-dict: {type(result)}")
            return "Sorry, I had a technical issue. Please try again."

        # Update state model from result
        state_model.chat_history = result.get("chat_history", state_model.chat_history)
        state_model.user_preferences = result.get("user_preferences", state_model.user_preferences)

        # Update trip details if changed
        for field in ["trip_id", "pickup_location", "drop_location", "trip_type",
                     "pickup_location_object", "drop_location_object",
                     "start_date", "end_date", "passenger_count", "booking_status"]:
            if result.get(field) is not None:
                setattr(state_model, field, result.get(field))

        state_model.last_bot_response = result.get("last_bot_response", state_model.last_bot_response)
        state_model.tool_calls = result.get("tool_calls", state_model.tool_calls)

        # Save updated state
        await save_user_state(user_id, state_model)

        # Extract response
        response = state_model.last_bot_response

        if not response or not response.strip():
            # Check last AI message
            for msg in reversed(state_model.chat_history):
                if hasattr(msg, 'content') and 'AI' in str(type(msg)):
                    if msg.content and msg.content.strip():
                        response = msg.content
                        break

        # Final fallback
        if not response or not response.strip():
            response = "I'm here to help you book a cab. Please tell me your pickup city, destination, and travel date."

        # Extend session TTL
        await redis_manager.extend_session(user_id)

        return response

    except asyncio.TimeoutError:
        logger.error(f"Agent timeout for {user_id}")
        return "The booking process is taking longer than expected. Please try again."
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return "I encountered an issue. Please try again or call support at +919403892230"


@app.post("/chat")
async def chat_with_bot(chat_request: ChatRequest):
    """
    Handles a chat message from a user and returns the bot's response.
    """
    try:
        customer_details = {
            "customer_id": chat_request.customer_id,
            "customer_name": chat_request.customer_name,
            "customer_profile": chat_request.customer_profile,
            "customer_phone": chat_request.customer_phone,
        }

        location_objects = {
            "pickupLocation": chat_request.pickupLocation,
            "dropLocation": chat_request.dropLocation
        }

        source = chat_request.source if chat_request.source else "app"

        response = await process_message_async(
            chat_request.user_id,
            chat_request.message,
            customer_details,
            source,
            location_objects
        )

        # Check if trip was created or cancelled
        trip_created = False
        trip_cancelled = False

        success_messages = [
            "great! we're reaching out to drivers",
            "you'll start getting quotes",
            "quotes in just a few minutes"
        ]

        cancel_messages = [
            "cancelled successfully",
            "trip has been cancelled"
        ]

        response_lower = response.lower()
        for msg in success_messages:
            if msg in response_lower:
                trip_created = True
                break

        for msg in cancel_messages:
            if msg in response_lower:
                trip_cancelled = True
                break

        return {
            "type": "text",
            "response": response,
            "trip_created": trip_created,
            "trip_cancelled": trip_cancelled,
            "source": chat_request.source
        }
    except Exception as e:
        return {
            "type": "error",
            "response": str(e),
            "trip_created": False,
            "trip_cancelled": False,
            "source": chat_request.source
        }


@app.get("/sessions")
async def get_all_sessions():
    """Get information about all active sessions"""
    active_users = await redis_manager.get_all_active_sessions()
    sessions_info = []

    for user_id in active_users:
        info = await redis_manager.get_session_info(user_id)
        if info:
            sessions_info.append(info)

    redis_health = await redis_manager.health_check()

    return {
        "total_active_sessions": len(active_users),
        "sessions": sessions_info,
        "fallback_storage_users": len(fallback_storage),
        "redis_health": redis_health
    }


@app.get("/health")
async def health():
    """Health check with Redis status"""
    redis_health = await redis_manager.health_check()

    return {
        "status": "healthy",
        "redis": redis_health,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def home():
    """Simple status page"""
    redis_health = await redis_manager.health_check()
    active_sessions = await redis_manager.get_all_active_sessions()

    return {
        "status": "running",
        "bot": "Cab Booking Assistant",
        "version": "5.0",
        "active_sessions": len(active_sessions),
        "fallback_storage_users": len(fallback_storage),
        "redis_status": redis_health.get("status"),
        "redis_available": redis_health.get("redis_available"),
        "endpoints": {
            "chat": "/chat (POST)",
            "sessions": "/sessions (GET)",
            "health": "/health (GET)"
        }
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
