# langgraph_agent/graph/nodes.py
"""Fixed graph nodes with proper filter processing for preferences"""

import json
import logging
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
llm = ChatVertexAI(model="gemini-2.0-flash", temperature=0.7)
llm_with_tools = llm.bind_tools(tools)


def extract_trip_details_from_message(message: str, current_date: str) -> Dict[str, Any]:
    """Extract trip details from user message"""
    extracted = {}
    message_lower = message.lower()

    # Common Indian cities
    cities = [
        "delhi", "mumbai", "bangalore", "bengaluru", "chennai", "kolkata",
        "hyderabad", "pune", "ahmedabad", "jaipur", "surat", "lucknow",
        "kanpur", "nagpur", "indore", "bhopal", "patna", "vadodara",
        "ghaziabad", "ludhiana", "agra", "nashik", "faridabad", "meerut",
        "rajkot", "varanasi", "srinagar", "aurangabad", "dhanbad", "amritsar",
        "gurgaon", "gurugram", "noida", "chandigarh", "mysore", "mysuru"
    ]

    # Find cities mentioned
    found_cities = []
    for city in cities:
        if city in message_lower:
            found_cities.append(city.title())

    # Determine pickup and drop from context
    if "from" in message_lower and "to" in message_lower:
        parts = message_lower.split("from")[1].split("to")
        if len(parts) >= 2:
            for city in cities:
                if city in parts[0]:
                    extracted["pickup_city"] = city.title()
                if city in parts[1]:
                    extracted["drop_city"] = city.title()
    elif " to " in message_lower or " se " in message_lower:
        if len(found_cities) >= 2:
            extracted["pickup_city"] = found_cities[0]
            extracted["drop_city"] = found_cities[1]

    # Extract trip type
    if "one-way" in message_lower or "one way" in message_lower or "oneway" in message_lower:
        extracted["trip_type"] = "one-way"
    elif "round-trip" in message_lower or "round trip" in message_lower or "roundtrip" in message_lower or "return" in message_lower:
        extracted["trip_type"] = "round-trip"

    # Extract date
    current = datetime.strptime(current_date, "%Y-%m-%d")

    if "tomorrow" in message_lower or "kal" in message_lower:
        extracted["start_date"] = (current + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "today" in message_lower or "aaj" in message_lower:
        extracted["start_date"] = current_date
    elif "day after tomorrow" in message_lower or "parso" in message_lower:
        extracted["start_date"] = (current + timedelta(days=2)).strftime("%Y-%m-%d")

    logger.info(f"Extracted trip details: {extracted}")
    return extracted


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Agent node that processes messages and decides actions"""
    logger.info("\n" + "="*50)
    logger.info("AGENT NODE EXECUTION")
    logger.info("="*50)

    # Log current state
    logger.info("Current State:")
    logger.info(f"  - Customer ID: {state.get('customer_id')}")
    logger.info(f"  - Trip ID: {state.get('trip_id')}")
    logger.info(f"  - Route: {state.get('pickup_location')} to {state.get('drop_location')}")
    logger.info(f"  - Booking Status: {state.get('booking_status')}")
    logger.info(f"  - Drivers Notified: {len(state.get('driver_ids_notified', []))}")

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Enhanced prompt with filter instructions
    enhanced_prompt = bot_prompt.format(current_date=current_date_str) + """

## CRITICAL FILTER PROCESSING RULES:

When user provides preferences, you MUST correctly map them to the exact filter parameters:

**VEHICLE TYPES (CRITICAL):**
- User says "SUV" or "Innova" or "Ertiga" → filters: {"vehicleTypes": ["suv"]}
- User says "Sedan" or "Dzire" or "Etios" → filters: {"vehicleTypes": ["sedan"]}
- User says "Hatchback" or "Swift" or "i20" → filters: {"vehicleTypes": ["hatchback"]}
- User says "Tempo Traveller" → filters: {"vehicleTypes": ["tempoTraveller12Seater"]}
- Multiple vehicles → filters: {"vehicleTypes": ["suv", "sedan"]}

**BOOLEAN PREFERENCES:**
- "married" or "married drivers" → filters: {"married": true}
- "pet friendly" or "allows pets" → filters: {"isPetAllowed": true}
- "verified" or "verified drivers" → filters: {"verified": true}
- "handicap accessible" → filters: {"allowHandicappedPersons": true}
- "for events" or "wedding" → filters: {"availableForDrivingInEventWedding": true}
- "personal car" → filters: {"availableForCustomersPersonalCar": true}

**LANGUAGE:**
- "Hindi speaking" → filters: {"verifiedLanguages": ["Hindi"]}
- "English and Punjabi" → filters: {"verifiedLanguages": ["English", "Punjabi"]}

**EXPERIENCE/AGE:**
- "experienced" or "5+ years" → filters: {"minExperience": 5}
- "very experienced" or "10+ years" → filters: {"minExperience": 10}
- "young drivers" → filters: {"maxAge": 30}
- "middle aged" → filters: {"minAge": 30, "maxAge": 50}

**GENDER:**
- "male drivers" → filters: {"gender": "male"}
- "female drivers" → filters: {"gender": "female"}

**COMBINING FILTERS:**
When user gives multiple preferences like "SUV and married drivers who speak Hindi":
filters: {
    "vehicleTypes": ["suv"],
    "married": true,
    "verifiedLanguages": ["Hindi"]
}

ALWAYS process ALL preferences mentioned by the user into the correct filter format!
"""

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Check if this is a new conversation and extract trip details
    if len(chat_history) == 1 and isinstance(chat_history[0], HumanMessage):
        user_message = chat_history[0].content
        extracted = extract_trip_details_from_message(user_message, current_date_str)

        # Update state with extracted details if not already set
        if extracted.get("pickup_city") and not state.get("pickup_location"):
            state["pickup_location"] = extracted["pickup_city"]
            logger.info(f"  Setting pickup_location: {extracted['pickup_city']}")

        if extracted.get("drop_city") and not state.get("drop_location"):
            state["drop_location"] = extracted["drop_city"]
            logger.info(f"  Setting drop_location: {extracted['drop_city']}")

        if extracted.get("trip_type") and not state.get("trip_type"):
            state["trip_type"] = extracted["trip_type"]
            logger.info(f"  Setting trip_type: {extracted['trip_type']}")

        if extracted.get("start_date") and not state.get("start_date"):
            state["start_date"] = extracted["start_date"]
            logger.info(f"  Setting start_date: {extracted['start_date']}")

    # Build messages for LLM with enhanced prompt
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
                # Agent wants to call tools - log the tool calls for debugging
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
            # Prepare tool arguments with enhanced filter validation
            prepared_args = prepare_tool_arguments(tool_name, tool_args, state_updates)

            logger.info("\n📞 CALLING TOOL FUNCTION...")
            logger.info(f"📨 Final Prepared Arguments: {json.dumps(prepared_args, indent=2)}")

            # Execute the tool
            output = tool_to_call.invoke(prepared_args)
            logger.info(f"\n✅ Tool execution completed")

            # Update state based on tool output
            update_state_from_tool_output(tool_name, output, prepared_args, state_updates)

            # Format output for LLM
            if tool_name == "create_trip_and_check_availability":
                if output.get("status") == "success":
                    output_str = json.dumps({
                        "status": "success",
                        "message": output.get("message"),
                        "trip_id": output.get("trip_id"),
                        "drivers_notified": output.get("drivers_notified", 0),
                        "details": "Drivers are being notified based on preferences"
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

    # Update the chat history and clear the tool calls
    state_updates["chat_history"] = state.get("chat_history", []) + tool_messages
    state_updates["tool_calls"] = []

    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR COMPLETED")
    logger.info("="*50)

    return state_updates


def prepare_tool_arguments(tool_name: str, tool_args: Dict[str, Any], state: dict) -> Dict[str, Any]:
    """Prepare tool arguments with proper filter validation and processing"""
    logger.info("\n🔧 Preparing tool arguments with filter validation...")
    args = tool_args.copy()

    if tool_name == "create_trip_and_check_availability":
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

        # CRITICAL: Validate and process filters
        if "filters" in args and args["filters"]:
            logger.info(f"  🎯 Processing Filters from LLM:")
            logger.info(f"     Raw filters: {json.dumps(args['filters'], indent=2)}")

            # Validate filter structure
            validated_filters = validate_and_fix_filters(args["filters"])
            args["filters"] = validated_filters

            logger.info(f"     Validated filters: {json.dumps(validated_filters, indent=2)}")

    return args


def validate_and_fix_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix filter structure to ensure proper API compatibility
    """
    if not filters:
        return {}

    validated = {}

    # Vehicle types validation - ensure it's a list
    if "vehicleTypes" in filters:
        vehicle_value = filters["vehicleTypes"]
        if isinstance(vehicle_value, str):
            # Convert single string to list
            validated["vehicleTypes"] = [vehicle_value]
        elif isinstance(vehicle_value, list):
            # Keep as list
            validated["vehicleTypes"] = vehicle_value
        else:
            logger.warning(f"Invalid vehicleTypes format: {vehicle_value}")

    # Boolean filters - ensure they are actual booleans
    boolean_fields = [
        'married', 'isPetAllowed', 'verified', 'profileVerified',
        'allowHandicappedPersons', 'availableForCustomersPersonalCar',
        'availableForDrivingInEventWedding', 'availableForPartTimeFullTime'
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

    # Language validation - ensure it's a list
    if "verifiedLanguages" in filters:
        lang_value = filters["verifiedLanguages"]
        if isinstance(lang_value, str):
            validated["verifiedLanguages"] = [lang_value]
        elif isinstance(lang_value, list):
            validated["verifiedLanguages"] = lang_value

    # Integer fields validation
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
    """Update state based on tool output - only store driver IDs"""
    logger.info("\nUpdating state from tool output...")

    if tool_name == "create_trip_and_check_availability":
        if output.get("status") == "success":
            # Store trip details
            state["trip_id"] = output.get("trip_id")
            state["pickup_location"] = tool_args.get("pickup_city")
            state["drop_location"] = tool_args.get("drop_city")
            state["trip_type"] = tool_args.get("trip_type")
            state["start_date"] = tool_args.get("start_date")
            state["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")
            state["applied_filters"] = tool_args.get("filters", {})
            state["booking_status"] = "completed"

            # Store only driver IDs
            state["driver_ids_notified"] = output.get("driver_ids", [])

            logger.info(f"  ✅ State Updated:")
            logger.info(f"     - Trip ID: {state['trip_id']}")
            logger.info(f"     - Drivers Notified: {len(state['driver_ids_notified'])} driver IDs stored")
            logger.info(f"     - Applied Filters: {state['applied_filters']}")
            logger.info(f"     - Booking Status: {state['booking_status']}")


def process_filter_values(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy function - use validate_and_fix_filters instead"""
    return validate_and_fix_filters(filters)
