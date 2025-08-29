# langgraph_agent/graph/nodes.py
"""Enhanced intelligent agent with minimal questions and natural conversation flow"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from langchain_core.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI

from langgraph_agent.graph.sys_prompt import bot_prompt
from langgraph_agent.tools.drivers_tools import create_trip_and_check_availability
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tools list
tools = [create_trip_and_check_availability]

# Initialize LLM
llm = ChatVertexAI(model="gemini-2.5-flash", temperature=1)
llm_with_tools = llm.bind_tools(tools)


def is_driver_query(message: str) -> bool:
    """Check if the message is from a driver looking for duty/rides - STRICTER CHECK"""
    message_lower = message.lower()

    # STRICT driver-specific keywords - must be very clear driver intent
    strict_driver_indicators = [
        "i need duty", "i want duty", "duty chahiye", "duty milegi",
        "driver hun", "driver hoon", "i am driver", "i'm a driver",
        "i am a partner", "i'm a partner", "partner hun",
        "duty from", "duty to", "koi duty", "any duty",
        "duty available", "passenger chahiye", "i need passengers",
        "i drive for", "main driver", "i am cab driver"
    ]

    # Check if any strict driver indicator is present
    for indicator in strict_driver_indicators:
        if indicator in message_lower:
            return True

    # EXCLUDE customer phrases - if these are present, it's NOT a driver
    customer_indicators = [
        "i need a ride", "i want a ride", "book a ride", "need a cab",
        "i need a cab", "i want a cab", "book a cab", "need taxi",
        "i need to go", "i want to go", "i have to travel",
        "pick me", "drop me", "i am traveling", "i'm traveling"
    ]

    # If any customer indicator is present, it's definitely NOT a driver
    for indicator in customer_indicators:
        if indicator in message_lower:
            return False

    return False


def detect_language(message: str) -> str:
    """Detect the language/style of user's message"""
    message_lower = message.lower()

    # Hindi/Hinglish indicators
    hindi_words = ["chahiye", "hai", "hoon", "hun", "kya", "kab", "kaise", "kitne",
                   "kal", "aaj", "parso", "gaadi", "log", "bhai", "ji", "kripya",
                   "dhanyawad", "shukriya", "namaste", "aapka", "mujhe", "mere"]

    hindi_count = sum(1 for word in hindi_words if word in message_lower)

    if hindi_count >= 2:
        return "hinglish"
    elif any(word in message_lower for word in ["please", "thank", "hello", "hi", "need", "want"]):
        return "english"
    else:
        return "english"  # default


def check_if_trip_details_changed(state: Dict[str, Any], extracted: Dict[str, Any]) -> bool:
    """Check if core trip details have changed"""
    # Check if any core trip detail has changed
    if extracted.get("pickup_city") and state.get("pickup_location"):
        if extracted["pickup_city"].lower() != state["pickup_location"].lower():
            logger.info(f"  🔄 Pickup location changed: {state['pickup_location']} → {extracted['pickup_city']}")
            return True

    if extracted.get("drop_city") and state.get("drop_location"):
        if extracted["drop_city"].lower() != state["drop_location"].lower():
            logger.info(f"  🔄 Drop location changed: {state['drop_location']} → {extracted['drop_city']}")
            return True

    if extracted.get("trip_type") and state.get("trip_type"):
        if extracted["trip_type"] != state["trip_type"]:
            logger.info(f"  🔄 Trip type changed: {state['trip_type']} → {extracted['trip_type']}")
            return True

    if extracted.get("start_date") and state.get("start_date"):
        if extracted["start_date"] != state["start_date"]:
            logger.info(f"  🔄 Date changed: {state['start_date']} → {extracted['start_date']}")
            return True

    return False


def infer_vehicle_from_context(message: str, current_filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intelligently infer vehicle type from user message context
    """
    message_lower = message.lower()
    filters = current_filters.copy() if current_filters else {}

    # Pattern to find numbers with context about people/passengers
    people_patterns = [
        r'(\d+)\s*(?:people|persons|passengers|pax|members|adults|children)',
        r'(?:for|need|want|require|book)\s*(?:a\s*)?(?:cab|taxi|car)\s*for\s*(\d+)',
        r'(?:we\s*are|we\'re)\s*(\d+)\s*(?:people|persons)?',
        r'(\d+)\s*(?:of us|log|jane wale)',
        r'(?:total|around|about|approximately)\s*(\d+)\s*(?:people|persons)?',
        r'(\d+)\s*(?:seater|seat)',
        r'family of\s*(\d+)',
        r'group of\s*(\d+)',
    ]

    passenger_count = None
    for pattern in people_patterns:
        match = re.search(pattern, message_lower)
        if match:
            passenger_count = int(match.group(1))
            break

    # Check for implicit passenger count indicators
    if not passenger_count:
        if any(word in message_lower for word in ["family", "group", "team", "friends"]):
            # Assume a small group if not specified
            passenger_count = 4
        elif any(word in message_lower for word in ["couple", "wife and", "husband and", "partner and"]):
            passenger_count = 2
        elif any(word in message_lower for word in ["alone", "solo", "myself", "just me"]):
            passenger_count = 1

    # Handle passenger count based rules
    if passenger_count:
        logger.info(f"  🚗 Detected/Inferred passenger count: {passenger_count}")

        if passenger_count >= 9:
            # 9 or more -> 12 seater tempo
            filters["vehicleTypes"] = ["tempoTraveller12Seater"]
            filters["auto_inferred"] = True
            filters["passenger_count"] = passenger_count
            logger.info(f"  📋 Auto-selected: 12-seater Tempo Traveller for {passenger_count} passengers")

        elif passenger_count >= 5:
            # 5-8 -> SUV
            filters["vehicleTypes"] = ["suv"]
            filters["auto_inferred"] = True
            filters["passenger_count"] = passenger_count
            logger.info(f"  📋 Auto-selected: SUV for {passenger_count} passengers")
        else:
            # 1-4 passengers - don't auto-select vehicle, but note the count
            filters["passenger_count"] = passenger_count
            logger.info(f"  📋 {passenger_count} passengers noted - will ask preferences naturally")

    # Check for explicit vehicle mentions (override passenger-based selection if explicit)
    vehicle_mappings = {
        "suv": ["suv", "innova", "ertiga", "xuv", "scorpio", "fortuner", "crysta", "hexa", "safari"],
        "sedan": ["sedan", "dzire", "etios", "amaze", "city", "verna", "ciaz", "rapid", "vento"],
        "hatchback": ["hatchback", "swift", "i20", "i10", "wagon", "alto", "baleno", "jazz", "polo"],
        "tempoTraveller12Seater": ["tempo", "traveller", "12 seater", "12-seater", "minibus", "van"]
    }

    for vehicle_type, keywords in vehicle_mappings.items():
        for keyword in keywords:
            if keyword in message_lower:
                filters["vehicleTypes"] = [vehicle_type]
                filters["explicit_vehicle"] = True
                logger.info(f"  📋 Explicit vehicle preference detected: {vehicle_type}")
                return filters  # Return immediately if explicit vehicle mentioned

    # Handle vague size mentions only if no explicit vehicle or passenger count
    if not filters.get("vehicleTypes") and not passenger_count:
        if "big car" in message_lower or "large car" in message_lower or "badi gaadi" in message_lower:
            filters["vehicleTypes"] = ["suv"]  # Default to SUV for "big car"
            logger.info("  📋 'Big car' mentioned - defaulting to SUV")
        elif "small car" in message_lower or "choti gaadi" in message_lower or "compact" in message_lower:
            filters["vehicleTypes"] = ["hatchback"]
            logger.info("  📋 Small/compact car requested - selected Hatchback")
        elif any(word in message_lower for word in ["comfortable", "luxury", "premium"]):
            filters["vehicleTypes"] = ["suv"]
            logger.info("  📋 Comfort/luxury requested - selected SUV")
        elif any(word in message_lower for word in ["budget", "cheap", "economical", "affordable"]):
            filters["vehicleTypes"] = ["hatchback"]
            logger.info("  📋 Budget option requested - selected Hatchback")

    return filters


def extract_trip_details_from_message(message: str, current_date: str) -> Dict[str, Any]:
    """Extract all possible trip details from user message"""
    extracted = {}
    message_lower = message.lower()

    # More flexible city extraction
    # Pattern 1: "from X to Y" or "X to Y" or "X se Y"
    city_patterns = [
        r'(?:from\s+)?([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:to|se)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
        r'(?:need|want|book).*?(?:from\s+)?([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:to|se)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
    ]

    for pattern in city_patterns:
        match = re.search(pattern, message_lower)
        if match:
            pickup = match.group(1).strip()
            drop = match.group(2).strip()

            # Filter out common words that aren't cities
            common_words = ['cab', 'taxi', 'car', 'trip', 'ride', 'need', 'want', 'book', 'a', 'the', 'me']
            if pickup not in common_words and drop not in common_words:
                extracted["pickup_city"] = ' '.join(word.capitalize() for word in pickup.split())
                extracted["drop_city"] = ' '.join(word.capitalize() for word in drop.split())
                logger.info(f"  Extracted cities: {extracted['pickup_city']} to {extracted['drop_city']}")
                break

    # Extract trip type
    if any(term in message_lower for term in ["one-way", "one way", "oneway", "single", "one side"]):
        extracted["trip_type"] = "one-way"
    elif any(term in message_lower for term in ["round-trip", "round trip", "roundtrip", "return", "two way", "both way"]):
        extracted["trip_type"] = "round-trip"
    # If not specified, we'll ask later but default to one-way for now
    elif extracted.get("pickup_city") and extracted.get("drop_city"):
        # Don't set trip type, let agent ask if needed
        pass

    # Extract date with more patterns
    current = datetime.strptime(current_date, "%Y-%m-%d")

    # Tomorrow patterns
    if any(word in message_lower for word in ["tomorrow", "kal", "next day"]):
        extracted["start_date"] = (current + timedelta(days=1)).strftime("%Y-%m-%d")
    # Today patterns
    elif any(word in message_lower for word in ["today", "aaj", "now", "immediate", "urgent"]):
        extracted["start_date"] = current_date
    # Day after tomorrow
    elif any(phrase in message_lower for phrase in ["day after tomorrow", "parso", "day after"]):
        extracted["start_date"] = (current + timedelta(days=2)).strftime("%Y-%m-%d")
    # Specific date patterns (e.g., "on 25th", "25 dec", etc.)
    else:
        # Try to find date patterns
        date_match = re.search(r'(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?(?:\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))?', message_lower)
        if date_match:
            day = int(date_match.group(1))
            month = date_match.group(2)

            if month:
                month_map = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month_num = month_map.get(month, current.month)
                year = current.year

                # If the date has passed this year, assume next year
                try:
                    target_date = datetime(year, month_num, day)
                    if target_date < current:
                        target_date = datetime(year + 1, month_num, day)
                    extracted["start_date"] = target_date.strftime("%Y-%m-%d")
                except ValueError:
                    pass  # Invalid date, skip
            else:
                # Just day number, assume current month
                try:
                    target_date = datetime(current.year, current.month, day)
                    if target_date < current:
                        # If date has passed, assume next month
                        if current.month == 12:
                            target_date = datetime(current.year + 1, 1, day)
                        else:
                            target_date = datetime(current.year, current.month + 1, day)
                    extracted["start_date"] = target_date.strftime("%Y-%m-%d")
                except ValueError:
                    pass  # Invalid date, skip

    # Apply vehicle inference
    vehicle_filters = infer_vehicle_from_context(message, {})
    if vehicle_filters:
        extracted["inferred_filters"] = vehicle_filters

    # Extract any other preferences mentioned
    preferences = {}

    # Language preferences
    languages = ["hindi", "english", "punjabi", "gujarati", "marathi", "tamil", "telugu", "bengali"]
    mentioned_langs = [lang.capitalize() for lang in languages if lang in message_lower]
    if mentioned_langs:
        preferences["verifiedLanguages"] = mentioned_langs

    # Driver preferences
    if any(word in message_lower for word in ["experienced", "expert", "senior"]):
        preferences["minExperience"] = 5
    if any(word in message_lower for word in ["very experienced", "highly experienced"]):
        preferences["minExperience"] = 10
    if "married" in message_lower:
        preferences["married"] = True
    if any(word in message_lower for word in ["pet", "dog", "cat"]):
        preferences["isPetAllowed"] = True
    if any(word in message_lower for word in ["verified", "certified"]):
        preferences["verified"] = True
    if any(word in message_lower for word in ["non-smoker", "nonsmoker", "no smoking"]):
        preferences["non_smoker"] = True
    if "smoker" in message_lower and "non" not in message_lower:
        preferences["smoker"] = True

    # Check for "more drivers" or "additional drivers" requests
    if any(phrase in message_lower for phrase in ["more drivers", "additional drivers", "other drivers", "more options"]):
        preferences["request_more_drivers"] = True

    if preferences:
        if "inferred_filters" in extracted:
            extracted["inferred_filters"].update(preferences)
        else:
            extracted["inferred_filters"] = preferences

    logger.info(f"Extracted trip details: {extracted}")
    return extracted


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Intelligent agent node that minimizes questions and maximizes efficiency"""
    logger.info("\n" + "="*50)
    logger.info("AGENT NODE EXECUTION")
    logger.info("="*50)

    # Log current state
    logger.info("Current State:")
    logger.info(f"  - Customer ID: {state.get('customer_id')}")
    logger.info(f"  - Trip ID: {state.get('trip_id')}")
    logger.info(f"  - Route: {state.get('pickup_location')} to {state.get('drop_location')}")
    logger.info(f"  - Booking Status: {state.get('booking_status')}")
    logger.info(f"  - Current Filters: {state.get('applied_filters', {})}")

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Check for driver queries first - STRICTER CHECK
    if chat_history and isinstance(chat_history[-1], HumanMessage):
        user_message = chat_history[-1].content

        if is_driver_query(user_message):
            logger.info("  🚗 Detected DRIVER query - redirecting to partner support")

            language = detect_language(user_message)
            if language == "hinglish":
                response = "Namaste! Main sirf customer bookings handle karta hun. Partner/driver queries ke liye kripya +919403890306 par call karein. Dhanyawad!"
            else:
                response = "Hello! I handle customer bookings only. For partner/driver queries, please call +919403890306. Thank you!"

            return {
                **state,
                "chat_history": chat_history + [AIMessage(content=response)],
                "last_bot_response": response,
                "tool_calls": [],
            }

    if chat_history and isinstance(chat_history[-1], HumanMessage):
        current_message = chat_history[-1].content
        message_lower = current_message.lower()

        # Handle common questions about car details
        if any(phrase in message_lower for phrase in [
            "which car will come", "what car will come", "which vehicle",
            "car details", "driver details", "who will pick",
            "which driver", "driver name", "car number"
        ]):
            response = "Once drivers accept your request, you'll receive their details including name, car model, and pricing. You can then call them directly to discuss further details and confirm your booking."
            return {
                **state,
                "chat_history": chat_history + [AIMessage(content=response)],
                "last_bot_response": response,
                "tool_calls": [],
            }

        # Extract all details from current message
        extracted = extract_trip_details_from_message(current_message, current_date_str)

        # Check if trip details have changed (requires new trip)
        trip_changed = check_if_trip_details_changed(state, extracted)

        # If trip changed, reset the trip ID and booking status
        if trip_changed:
            logger.info("  🔄 Trip details changed - will create new trip")
            state["trip_id"] = None
            state["booking_status"] = None
            state["driver_ids_notified"] = []

        # Handle "more drivers" request when trip already exists
        if extracted.get("inferred_filters", {}).get("request_more_drivers") and state.get("trip_id") and state.get("booking_status") == "completed":
            logger.info("  📋 User requesting more drivers for existing trip")
            # Don't reset trip, just update preferences flag
            extracted["inferred_filters"]["fetch_more_drivers"] = True

        # Update state with extracted details
        if extracted.get("pickup_city") and (not state.get("pickup_location") or trip_changed):
            state["pickup_location"] = extracted["pickup_city"]
            logger.info(f"  Setting pickup: {extracted['pickup_city']}")

        if extracted.get("drop_city") and (not state.get("drop_location") or trip_changed):
            state["drop_location"] = extracted["drop_city"]
            logger.info(f"  Setting drop: {extracted['drop_city']}")

        if extracted.get("trip_type") and (not state.get("trip_type") or trip_changed):
            state["trip_type"] = extracted["trip_type"]
            logger.info(f"  Setting trip type: {extracted['trip_type']}")

        if extracted.get("start_date") and (not state.get("start_date") or trip_changed):
            state["start_date"] = extracted["start_date"]
            logger.info(f"  Setting date: {extracted['start_date']}")

        # Update filters (merge with existing)
        if extracted.get("inferred_filters"):
            existing_filters = state.get("applied_filters", {})
            merged_filters = {**existing_filters, **extracted["inferred_filters"]}
            state["applied_filters"] = merged_filters
            logger.info(f"  Updated filters: {merged_filters}")

    # Build enhanced prompt with smart rules
    applied_filters_str = json.dumps(state.get('applied_filters', {}))

    # The comprehensive list of preferences users can choose
    preferences_list = """ Sedan, SUV, Punjabi-speaking, Gujarati-speaking, under 30, 10+ yrs experience, married, or pet-friendly."""

    enhanced_prompt = bot_prompt.format(
        current_date=current_date_str,
        preferences_list=preferences_list
    ) + f"""

## ULTRA-SMART BOOKING RULES:

### CRITICAL: PREFERENCE COMMUNICATION
**ALWAYS tell users what preferences they can choose from:**
When asking about preferences, ALWAYS use this format:
"Do you have any specific preferences — like {preferences_list}?"

Never just ask "Any preferences?" without listing options!

### TRIP CHANGE DETECTION:
- Trip ID exists: {state.get('trip_id')}
- Booking completed: {state.get('booking_status') == 'completed'}
- If trip details changed (pickup/drop/date/type), create NEW trip
- If only preferences changed, use EXISTING trip and fetch more drivers

### MINIMIZE QUESTIONS - MAXIMIZE EFFICIENCY:
1. **NEVER ask for information already provided** - Check state for pickup, drop, date, trip type
2. **Extract everything possible** from user's message before asking anything
3. **Group missing information** - Ask for all missing items in ONE question
4. **Smart defaults when appropriate**:
   - No passenger count mentioned = Assume 1-2 passengers, proceed without asking vehicle type
   - No trip type mentioned = Ask along with other missing info
   - No date mentioned = Ask along with other missing info

### VEHICLE SELECTION INTELLIGENCE:

**AUTO-SELECT WITHOUT ASKING:**
- 9+ passengers → 12-seater Tempo Traveller
- 5-8 passengers → SUV
- Explicit vehicle mention → Use that vehicle
- "big car" → SUV
- "small car" → Hatchback
- "budget" → Hatchback
- "comfortable"/"luxury" → SUV

**FOR 1-4 PASSENGERS OR NO COUNT:**
- DON'T ask "which vehicle type"
- Instead ask naturally with preference options listed

### SMART CONVERSATION FLOW:

**Current State Check:**
- Pickup: {state.get('pickup_location', 'Not set')}
- Drop: {state.get('drop_location', 'Not set')}
- Date: {state.get('start_date', 'Not set')}
- Trip Type: {state.get('trip_type', 'Not set')}
- Trip ID: {state.get('trip_id', 'Not created yet')}
- Booking Status: {state.get('booking_status', 'Not started')}
- Filters: {applied_filters_str}

**Response Strategy:**
1. If ALL critical info available (pickup, drop, date) → Jump to preferences WITH OPTIONS
2. If SOME info missing → Ask ONLY for missing info in one natural question
3. If vehicle auto-selected → Mention it casually, don't make it a big deal
4. Keep responses short, natural, and contextual

### NATURAL LANGUAGE PATTERNS:

**When everything is provided:**
"Perfect! [Optional: mention auto-selected vehicle if 5+ passengers]. Do you have any specific preferences — like {preferences_list}?"

**When asking for missing info (examples):**
- Missing date only: "When would you like to travel?"
- Missing date + trip type: "When are you planning to travel, and will it be one-way or round trip?"
- Missing pickup: "Where will you be starting from?"

**After booking completion:**
NEVER say "I have notified 25 drivers"
Instead say: "I'm connecting with drivers for prices and availability. You'll start receiving driver details with prices shortly. This may take a few minutes."

**NEVER say things like:**
- "I can help you book" (when they already asked for booking)
- "Where would you like to travel from and to?" (when already provided)
- "Which vehicle type would you prefer?" (deduce it or ask preferences generally WITH OPTIONS)
- "I have sent request to X drivers" (too technical)

### PREFERENCE COLLECTION:

**Smart preference ask (after getting trip details):**
- For 5+ passengers with auto-selected vehicle:
  "I'll arrange a [vehicle type] for your group. Do you have any other preferences — like {preferences_list}?"

- For 1-4 passengers or no count:
  "Do you have any specific preferences — like {preferences_list}?"

- When they say "no preferences":
  Immediately proceed with booking, don't ask again

### HANDLING MORE DRIVERS REQUEST:
- If user asks for more drivers AFTER booking is complete
- Check if trip details are same
- If same, fetch more drivers with updated preferences
- this time make sure to update the page number by 1 ex: previous page was 1 so now it should be 2
    otherwise it will refetch same drivers and send them same request again
- Say: "I'll connect with additional drivers based on your preferences. You'll receive more options shortly."

### CRITICAL: ALWAYS INCLUDE FILTERS IN TOOL CALL
Current filters in state: {applied_filters_str}
- If vehicle was auto-selected or mentioned, MUST include in tool call
- Merge state filters with any new preferences before calling tool
- If fetching more drivers for same trip, include "fetch_more_drivers": true flag

### CUSTOMER VS DRIVER DETECTION:
- Be VERY careful - "I need a ride" = CUSTOMER, not driver
- Only treat as driver if they say "I need duty" or "I need passengers"
- Default assumption: Always treat as customer unless explicitly driver language

Remember: Be smart, efficient, and natural. Every extra question is friction - minimize it! Always list preference options when asking!
"""

    # Build messages for LLM
    messages = [SystemMessage(content=enhanced_prompt)]

    if chat_history:
        messages.extend(chat_history)
        logger.info(f"  - Chat History Length: {len(chat_history)}")

    # Get LLM response
    try:
        logger.info("\nInvoking LLM...")
        ai_response = llm_with_tools.invoke(messages)

        # Update chat history
        updated_history = chat_history + [ai_response]

        # Check if the response has tool_calls
        if isinstance(ai_response, AIMessage):
            if not ai_response.tool_calls:
                # Direct response
                logger.info("✅ Agent provided direct response")
                return {
                    **state,
                    "chat_history": updated_history,
                    "last_bot_response": ai_response.content,
                    "tool_calls": [],
                }
            else:
                # Agent wants to call tools
                logger.info(f"🔧 Agent requesting tool calls")
                for tool_call in ai_response.tool_calls:
                    logger.info(f"  Tool: {tool_call.get('name')}")
                    logger.info(f"  Args: {json.dumps(tool_call.get('args', {}), indent=2)}")

                return {
                    **state,
                    "chat_history": updated_history,
                    "tool_calls": ai_response.tool_calls,
                }
        else:
            return {
                **state,
                "chat_history": updated_history,
                "last_bot_response": str(ai_response.content) if hasattr(ai_response, 'content') else str(ai_response),
                "tool_calls": [],
            }

    except Exception as e:
        logger.error(f"❌ Error in agent_node: {e}", exc_info=True)
        return {
            **state,
            "last_bot_response": "I apologize, but I encountered an issue. Please try again.",
            "tool_calls": [],
        }


def tool_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tools requested by the agent"""
    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR NODE")
    logger.info("="*50)

    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        logger.warning("⚠️ No tool_calls in state.")
        return state

    tool_map = {tool.name: tool for tool in tools}
    tool_messages = []
    state_updates = dict(state)

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")

        logger.info(f"\n🔧 Executing tool: {tool_name}")
        logger.info(f"📋 Raw Tool Arguments: {json.dumps(tool_args, indent=2)}")

        tool_to_call = tool_map.get(tool_name)
        if not tool_to_call:
            error_msg = f"Error: Tool '{tool_name}' not found."
            logger.error(f"❌ {error_msg}")
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )
            continue

        try:
            # Prepare tool arguments
            prepared_args = prepare_tool_arguments(tool_name, tool_args, state_updates)

            logger.info("\n📞 CALLING TOOL FUNCTION...")
            logger.info(f"📨 Final Prepared Arguments: {json.dumps(prepared_args, indent=2)}")

            # Execute the tool
            output = tool_to_call.invoke(prepared_args)
            logger.info(f"\n✅ Tool execution completed")

            # Update state based on tool output
            update_state_from_tool_output(tool_name, output, prepared_args, state_updates)

            # Format output for LLM - ENHANCED MESSAGE
            if tool_name == "create_trip_and_check_availability":
                if output.get("status") == "success":
                    # Don't mention number of drivers
                    output_str = json.dumps({
                        "status": "success",
                        "message": "I'm connecting with drivers for prices and availability. You'll start receiving driver details with prices shortly. This may take a few minutes.",
                        "trip_id": output.get("trip_id"),
                        "booking_confirmed": True
                    })
                    logger.info(f"✅ SUCCESS: Trip {output.get('trip_id')} created, {output.get('drivers_notified')} drivers notified")
                else:
                    output_str = json.dumps(output)
            else:
                output_str = json.dumps(output) if isinstance(output, dict) else str(output)

            tool_messages.append(
                ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
            )

        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_name}: {e}", exc_info=True)
            tool_messages.append(
                ToolMessage(
                    content=f"Error: Failed to process your request. Please try again.",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )

    # Update the chat history
    state_updates["chat_history"] = state.get("chat_history", []) + tool_messages
    state_updates["tool_calls"] = []

    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR COMPLETED")
    logger.info("="*50)

    return state_updates


def prepare_tool_arguments(tool_name: str, tool_args: Dict[str, Any], state: dict) -> Dict[str, Any]:
    """Prepare tool arguments with smart filter merging and trip management"""
    logger.info("\n🔧 Preparing tool arguments...")
    args = tool_args.copy()

    if tool_name == "create_trip_and_check_availability":
        # Check if we should reuse existing trip
        if state.get("trip_id") and state.get("booking_status") == "completed":
            # Check if core trip details match
            if (args.get("pickup_city") == state.get("pickup_location") and
                args.get("drop_city") == state.get("drop_location") and
                args.get("trip_type") == state.get("trip_type") and
                args.get("start_date") == state.get("start_date")):

                logger.info(f"  ♻️ Reusing existing trip ID: {state['trip_id']}")
                args["existing_trip_id"] = state["trip_id"]
                args["fetch_more_drivers"] = True

        # Add customer details from state
        customer_details = {
            "id": state.get("customer_id"),
            "name": state.get("customer_name"),
            "phone": state.get("customer_phone"),
            "profile_image": state.get("customer_profile", ""),
        }
        args["customer_details"] = customer_details

        logger.info(f"  Customer: {customer_details['name']} (ID: {customer_details['id']})")
        logger.info(f"  Route: {args.get('pickup_city')} to {args.get('drop_city')}")

        # CRITICAL: Merge filters from state with tool args
        state_filters = state.get("applied_filters", {})
        tool_filters = args.get("filters", {})

        # Merge filters intelligently
        merged_filters = {}

        # Add state filters (auto-inferred)
        if state_filters:
            logger.info(f"  🎯 State filters: {state_filters}")
            for key, value in state_filters.items():
                if key not in ['auto_inferred', 'passenger_count', 'needs_clarification', 'explicit_vehicle', 'request_more_drivers', 'fetch_more_drivers']:
                    merged_filters[key] = value

        # Add tool filters (from LLM)
        if tool_filters:
            logger.info(f"  🎯 Tool filters: {tool_filters}")
            for key, value in tool_filters.items():
                # Don't override vehicle if explicitly set in state
                if key == "vehicleTypes" and "vehicleTypes" in merged_filters and state_filters.get("explicit_vehicle"):
                    continue
                merged_filters[key] = value

        if merged_filters:
            logger.info(f"  🎯 Merged filters: {merged_filters}")
            # Validate filter structure
            validated_filters = validate_and_fix_filters(merged_filters)
            args["filters"] = validated_filters
            logger.info(f"  ✅ Validated filters: {validated_filters}")
        else:
            args["filters"] = {}

    return args


def validate_and_fix_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and fix filter structure for API compatibility"""
    if not filters:
        return {}

    validated = {}

    # Vehicle types validation
    if "vehicleTypes" in filters:
        vehicle_value = filters["vehicleTypes"]
        if isinstance(vehicle_value, str):
            validated["vehicleTypes"] = [vehicle_value]
        elif isinstance(vehicle_value, list):
            validated["vehicleTypes"] = vehicle_value
        else:
            logger.warning(f"Invalid vehicleTypes format: {vehicle_value}")

    # Boolean filters
    boolean_fields = [
        'married', 'isPetAllowed', 'verified', 'profileVerified',
        'allowHandicappedPersons', 'availableForCustomersPersonalCar',
        'availableForDrivingInEventWedding', 'availableForPartTimeFullTime',
        'non_smoker', 'smoker'
    ]

    for field in boolean_fields:
        if field in filters:
            value = filters[field]
            if isinstance(value, bool):
                validated[field] = value
            elif isinstance(value, str):
                validated[field] = value.lower() in ['true', '1', 'yes']
            else:
                validated[field] = bool(value)

    # Language validation
    if "verifiedLanguages" in filters:
        lang_value = filters["verifiedLanguages"]
        if isinstance(lang_value, str):
            validated["verifiedLanguages"] = [lang_value]
        elif isinstance(lang_value, list):
            validated["verifiedLanguages"] = lang_value

    # Integer fields
    integer_fields = ['minAge', 'maxAge', 'minExperience', 'minConnections', 'minDrivingExperience']
    for field in integer_fields:
        if field in filters:
            try:
                validated[field] = int(filters[field])
            except (ValueError, TypeError):
                logger.warning(f"Could not convert {field} to integer: {filters[field]}")

    # Gender validation
    if "gender" in filters:
        gender_value = str(filters["gender"]).lower()
        if gender_value in ['male', 'female']:
            validated["gender"] = gender_value

    return validated


def update_state_from_tool_output(
    tool_name: str,
    output: Any,
    tool_args: Dict[str, Any],
    state: dict
) -> None:
    """Update state based on tool output"""
    logger.info("\nUpdating state from tool output...")

    if tool_name == "create_trip_and_check_availability":
        if output.get("status") == "success":
            # Store trip details
            if output.get("trip_id"):
                state["trip_id"] = output.get("trip_id")
                state["pickup_location"] = tool_args.get("pickup_city")
                state["drop_location"] = tool_args.get("drop_city")
                state["trip_type"] = tool_args.get("trip_type")
                state["start_date"] = tool_args.get("start_date")
                state["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")

            # Always update filters and status
            state["applied_filters"] = tool_args.get("filters", {})
            state["booking_status"] = "completed"

            # Append new driver IDs if fetching more
            new_driver_ids = output.get("driver_ids", [])
            if tool_args.get("fetch_more_drivers"):
                existing_ids = state.get("driver_ids_notified", [])
                state["driver_ids_notified"] = existing_ids + new_driver_ids
            else:
                state["driver_ids_notified"] = new_driver_ids

            logger.info(f"  ✅ State Updated:")
            logger.info(f"     - Trip ID: {state['trip_id']}")
            logger.info(f"     - Total Drivers Notified: {len(state['driver_ids_notified'])}")
            logger.info(f"     - Applied Filters: {state['applied_filters']}")
            logger.info(f"     - Booking Status: {state['booking_status']}")
