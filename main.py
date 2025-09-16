# main.py
"""Simplified main application - focused on trip creation"""

import os
import asyncio
from typing import Optional, Dict
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

# Import your agent and state model
from langgraph_agent.graph.builder import app as cab_agent
from models.state_model import ConversationState
from services.redis_service import redis_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Lifecycle management for Redis
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - initialize and cleanup Redis"""
    # Startup
    logger.info("🚀 Starting up - initializing Redis connection...")
    await redis_manager.initialize()

    # Check Redis health
    health = await redis_manager.health_check()
    if health.get("redis_available"):
        logger.info(f"✅ Redis connected: {health.get('status')}")
    else:
        logger.warning("⚠️ Redis not available - using fallback storage")

    yield

    # Shutdown
    logger.info("🔚 Shutting down - closing Redis connections...")
    await redis_manager.close()


# Initialize FastAPI with lifespan
app = FastAPI(title="Cab Booking Bot - Simplified", lifespan=lifespan)

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


# --- Pydantic model for the /chat endpoint ---
class ChatRequest(BaseModel):
    user_id: str
    message: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_profile: Optional[str] = None
    customer_phone: Optional[str] = None


async def get_user_state(user_id: str, customer_details: dict = None) -> ConversationState:
    """Get or create user conversation state"""

    # First, try to get from Redis
    state = await redis_manager.get_session(user_id)

    if state:
        # Session exists in Redis
        logger.info(f"✅ Found existing session for {user_id}")

        # Update customer details if provided and changed
        if customer_details:
            updated = False
            if customer_details.get("customer_id") and state.customer_id != customer_details["customer_id"]:
                state.customer_id = customer_details["customer_id"]
                updated = True
            if customer_details.get("customer_name") and state.customer_name != customer_details["customer_name"]:
                state.customer_name = customer_details["customer_name"]
                updated = True
            if customer_details.get("customer_phone") and state.customer_phone != customer_details["customer_phone"]:
                state.customer_phone = customer_details["customer_phone"]
                updated = True
            if customer_details.get("customer_profile") and state.customer_profile != customer_details["customer_profile"]:
                state.customer_profile = customer_details["customer_profile"]
                updated = True

            if updated:
                await redis_manager.save_session(user_id, state)

        return state

    # No session in Redis, check fallback storage
    if user_id in fallback_storage:
        logger.info(f"📦 Using fallback storage for {user_id}")
        return fallback_storage[user_id]

    # Create new session WITH customer details
    logger.info(f"🆕 Creating new session for {user_id}")
    new_state = ConversationState(
        chat_history=[],
        user_preferences={},
        trip_id=None,
        pickup_location=None,
        drop_location=None,
        trip_type=None,
        start_date=None,
        end_date=None,
        customer_id=customer_details.get("customer_id") if customer_details else None,
        customer_name=customer_details.get("customer_name") if customer_details else None,
        customer_phone=customer_details.get("customer_phone") if customer_details else None,
        customer_profile=customer_details.get("customer_profile") if customer_details else None,
        last_bot_response=None,
        tool_calls=[],
        booking_status=None
    )

    # Save to Redis
    if not await redis_manager.save_session(user_id, new_state):
        # If Redis save fails, use fallback storage
        logger.warning(f"⚠️ Redis save failed, using fallback storage for {user_id}")
        fallback_storage[user_id] = new_state

    return new_state


async def save_user_state(user_id: str, state: ConversationState) -> bool:
    """Save user state to Redis with fallback"""
    success = await redis_manager.save_session(user_id, state)

    if not success:
        # Fallback to in-memory storage
        logger.warning(f"⚠️ Using fallback storage to save state for {user_id}")
        fallback_storage[user_id] = state

    return success


async def clear_user_session(user_id: str) -> bool:
    """Clear user session from Redis and fallback storage"""
    redis_deleted = await redis_manager.delete_session(user_id)

    # Also clear from fallback storage
    if user_id in fallback_storage:
        del fallback_storage[user_id]

    return redis_deleted


async def process_message_async(user_id: str, message: str, customer_details: dict = {}) -> str:
    """Process user message through simplified cab agent"""
    logger.info(f"🔄 Processing for {user_id}: {message}")

    # Get user state from Redis/fallback
    state_model = await get_user_state(user_id, customer_details)

    # Handle reset command
    if message.lower().strip() in ["reset", "start over", "restart"]:
        await clear_user_session(user_id)
        return "🔄 Let's start fresh! Please tell me your pickup city, destination, travel date, and whether it's a one-way or round trip."

    # Add message to chat history
    state_model.chat_history.append(HumanMessage(content=message))

    # Convert Pydantic model to dict for the agent
    state_dict = state_model.to_dict()

    # Process through agent
    try:
        logger.info(f"🤖 Invoking simplified agent...")

        # Run the sync agent in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        result = await asyncio.wait_for(
            loop.run_in_executor(None, cab_agent.invoke, state_dict),
            timeout=30.0  # Reduced timeout since we're not making multiple API calls
        )

        # Ensure result is valid
        if not isinstance(result, dict):
            logger.warning(f"⚠️ Agent returned non-dict: {type(result)}")
            return "Sorry, I had a technical issue. Please try again."

        # Update the Pydantic state model from the result
        state_model.chat_history = result.get("chat_history", state_model.chat_history)
        state_model.user_preferences = result.get("user_preferences", state_model.user_preferences)

        # Update trip details
        if result.get("trip_id") is not None:
            state_model.trip_id = result.get("trip_id")
        if result.get("pickup_location") is not None:
            state_model.pickup_location = result.get("pickup_location")
        if result.get("drop_location") is not None:
            state_model.drop_location = result.get("drop_location")
        if result.get("trip_type") is not None:
            state_model.trip_type = result.get("trip_type")
        if result.get("start_date") is not None:
            state_model.start_date = result.get("start_date")
        if result.get("end_date") is not None:
            state_model.end_date = result.get("end_date")

        state_model.last_bot_response = result.get("last_bot_response", state_model.last_bot_response)
        state_model.tool_calls = result.get("tool_calls", state_model.tool_calls)

        if result.get("booking_status") is not None:
            state_model.booking_status = result.get("booking_status")

        # Save updated state to Redis
        await save_user_state(user_id, state_model)

        logger.info(f"✅ State updated and saved for {user_id}")

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

        # Extend session TTL on successful interaction
        await redis_manager.extend_session(user_id)

        return response

    except asyncio.TimeoutError:
        logger.error(f"⏰ Agent call timed out for {user_id}")
        return "The booking process is taking longer than expected. Please try again."
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")
        return "I encountered an issue. Please try again or call support at +919403892230"


@app.post("/chat")
async def chat_with_bot(chat_request: ChatRequest):
    """
    Handles a chat message from a user and returns the bot's response.
    Simplified to focus on trip creation.
    """
    customer_details = {
        "customer_id": chat_request.customer_id,
        "customer_name": chat_request.customer_name,
        "customer_profile": chat_request.customer_profile,
        "customer_phone": chat_request.customer_phone,
    }

    response = await process_message_async(
        chat_request.user_id,
        chat_request.message,
        customer_details
    )

    # Check if trip was created (simplified check)
    trip_created = False
    success_messages = [
        "i've created your trip",
        "trip created",
        "you'll start receiving quotations",
        "drivers will contact you"
    ]

    response_lower = response.lower()
    for msg in success_messages:
        if msg in response_lower:
            trip_created = True
            break

    return {
        "type": "text",
        "response": response,
        "trip_created": trip_created  # Simplified flag
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
    """Simple status page with Redis info"""
    redis_health = await redis_manager.health_check()
    active_sessions = await redis_manager.get_all_active_sessions()

    return {
        "status": "running",
        "bot": "Cab Booking Assistant - Simplified",
        "version": "4.0",
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

    print("\n🚀 Starting Simplified Cab Booking Bot API v4.0")
    print("✨ Focused on trip creation with preferences")

    port = int(os.environ.get("PORT", 8080))
    print(f"📍 Server running on: http://localhost:{port}")
    print(f"💬 Chat API endpoint: http://localhost:{port}/chat")
    print(f"📈 View active sessions: http://localhost:{port}/sessions")

    uvicorn.run(app, host="0.0.0.0", port=port)
