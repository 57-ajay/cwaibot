# langgraph_agent/graph/nodes.py
"""LLM-driven intelligent agent with full multilingual support and error recovery"""

import json
import logging
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI

from langgraph_agent.graph.sys_prompt import bot_prompt
from langgraph_agent.tools.drivers_tools import create_trip_and_check_availability

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tools list
tools = [create_trip_and_check_availability]

# Initialize LLM - using Gemini for excellent multilingual support
llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.7)
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM-driven agent node that handles all languages and contexts naturally.
    Enhanced with error recovery and intelligent understanding.
    """
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
    logger.info(f"  - Current Page: {state.get('current_page', 1)}")
    logger.info(f"  - Error Count: {state.get('error_count', 0)}")
    logger.info(f"  - Last Error: {state.get('last_error_type', 'None')}")

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Check for error loops
    error_count = state.get("error_count", 0)
    last_error_type = state.get("last_error_type", "")

    # Build comprehensive prompt that handles everything
    enhanced_prompt = bot_prompt.format(
        current_date=current_date_str
    ) + f"""

## CURRENT CONVERSATION STATE:
- Pickup Location: {state.get('pickup_location', 'Not set')}
- Drop Location: {state.get('drop_location', 'Not set')}
- Travel Date: {state.get('start_date', 'Not set')}
- Trip Type: {state.get('trip_type', 'Not set')}
- Trip ID: {state.get('trip_id', 'None')}
- Booking Status: {state.get('booking_status', 'Not started')}
- Applied Filters: {json.dumps(state.get('applied_filters', {}))}
- Drivers Already Notified: {len(state.get('driver_ids_notified', []))}
- Current Page: {state.get('current_page', 1)}
- Error Count: {error_count}
- Last Error Type: {last_error_type}

## ERROR RECOVERY CONTEXT:
{f"WARNING: Same error occurred {error_count} times. Please try a different approach or simplify the search." if error_count > 1 else ""}
{f"CRITICAL: After {error_count} attempts, please remove complex filters and try basic search only." if error_count > 2 else ""}

## YOUR TASK:
Analyze the user's message and determine the appropriate response. Consider:

1. **Language**: Respond in the same language as the user (Hindi, Punjabi, English, etc.)

2. **Intelligent Intent Detection**:
   - "I need driver, I have car" → Customer needs driver for personal vehicle (availableForCustomersPersonalCar = true)
   - "Driver for wedding" → Customer needs event driver (availableForDrivingInEventWedding = true)
   - "Part time driver" → Long-term driver need (availableForPartTimeFullTime = true)
   - "Driver for disabled" → Special needs (allowHandicappedPersons = true)
   - NEVER say "I only handle customer bookings" for these - they ARE customer bookings!

3. **Information Extraction**: Extract from ANY language:
   - Cities (pickup and drop)
   - Dates and times
   - Trip type (one-way/round-trip)
   - Number of passengers
   - Vehicle preferences
   - Special service needs (personal car, wedding, etc.)
   - Driver preferences (language, experience, etc.)

4. **Smart Filter Mapping**:
   - "my car"/"own vehicle" → availableForCustomersPersonalCar = true
   - "wedding"/"shaadi" → availableForDrivingInEventWedding = true
   - "pet"/"dog"/"cat" → isPetAllowed = true
   - "female/male driver" → gender = "female"/"male"
   - "married driver" → married = true
   - "experienced" → minDrivingExperience = 5
   - "very experienced" → minDrivingExperience = 10
   - "verified"/"trusted" → verified = true, profileVerified = true

5. **Error Recovery Strategy**:
   - If error_count > 2: Simplify filters, remove complex requirements
   - If no drivers with filters: Suggest removing some preferences
   - If API errors: Try without filters
   - NEVER repeat the same failed operation more than twice

6. **State Management**:
   - If trip details change → Create new trip
   - If only requesting more drivers → Reuse trip, increment page
   - Track error attempts to prevent loops

7. **Tool Calling Rules**:
   - ONLY call tool when ALL trip details are available
   - If previous attempts failed, reduce filter complexity
   - Convert filters to API format properly:
     * vehicleTypes → vehicles (comma-separated string)
     * Language preference → language (single value)
     * Booleans → "true"/"false" strings
     * Special services → appropriate boolean flags

8. **Response Strategy**:
   - BE INTELLIGENT: Understand intent, not just literal words
   - AVOID LOOPS: If stuck, try different approach
   - MINIMIZE SUPPORT ESCALATION: Only mention support after exhausting alternatives
   - Success → Don't mention driver count

Remember: You are INTELLIGENT. Understand what users MEAN, not just what they say.
Adapt and help rather than deflecting to support. Find creative solutions.
"""

    # Build messages for LLM
    messages = [SystemMessage(content=enhanced_prompt)]

    if chat_history:
        messages.extend(chat_history)
        logger.info(f"  - Chat History Length: {len(chat_history)}")

    # Get LLM response
    try:
        logger.info("\nInvoking LLM for intelligent response...")
        ai_response = llm_with_tools.invoke(messages)

        # Update chat history
        updated_history = chat_history + [ai_response]

        # Check if the response has tool_calls
        if isinstance(ai_response, AIMessage):
            if not ai_response.tool_calls:
                # Direct response - reset error count since we're not stuck
                logger.info("✅ Agent provided direct response")

                return {
                    **state,
                    "chat_history": updated_history,
                    "last_bot_response": ai_response.content,
                    "tool_calls": [],
                    "error_count": 0,  # Reset error count on successful response
                    "last_error_type": ""
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
                "error_count": 0,  # Reset on successful response
                "last_error_type": ""
            }

    except Exception as e:
        logger.error(f"❌ Error in agent_node: {e}", exc_info=True)

        # Track error for loop prevention
        error_count = state.get("error_count", 0) + 1

        # Let LLM handle error message intelligently based on error count
        error_prompt = f"""
        There was a technical error (attempt {error_count}).

        If this is attempt 1-2: Provide a friendly message about trying again.
        If this is attempt 3+: Suggest simplifying the search or trying with basic requirements.
        Only mention support number (+919403892230) if error_count > 3.

        Be apologetic and helpful. Respond in the user's language.
        """

        try:
            error_response = llm.invoke([SystemMessage(content=error_prompt)] + chat_history[-1:] if chat_history else [])
            error_message = error_response.content
        except:
            if error_count > 3:
                error_message = "I apologize for the continued issues. Please call CabsWale Support at +919403892230 for immediate assistance."
            else:
                error_message = "I encountered an issue. Let me try a different approach to help you book your cab."

        return {
            **state,
            "last_bot_response": error_message,
            "tool_calls": [],
            "error_count": error_count,
            "last_error_type": "agent_error"
        }


def tool_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tools requested by the agent with enhanced error recovery"""
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

    # Track if this execution succeeds
    execution_successful = False

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")

        logger.info(f"\n🔧 Executing tool: {tool_name}")
        logger.info(f"📋 Tool Arguments from LLM: {json.dumps(tool_args, indent=2)}")

        tool_to_call = tool_map.get(tool_name)
        if not tool_to_call:
            error_msg = f"Tool '{tool_name}' not found. Let me try a different approach."
            logger.error(f"❌ {error_msg}")
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )
            continue

        try:
            # Check if we should simplify filters based on error count
            error_count = state_updates.get("error_count", 0)
            if error_count > 2 and "filters" in tool_args and tool_args["filters"]:
                logger.info(f"⚠️ Simplifying filters due to {error_count} previous errors")
                # Keep only basic filters
                original_filters = tool_args["filters"]
                simplified_filters = {}

                # Only keep vehicle type if specified
                if "vehicleTypes" in original_filters:
                    simplified_filters["vehicleTypes"] = original_filters["vehicleTypes"]
                elif "vehicles" in original_filters:
                    simplified_filters["vehicles"] = original_filters["vehicles"]

                tool_args["filters"] = simplified_filters
                logger.info(f"📋 Simplified filters: {simplified_filters}")

            # Prepare tool arguments
            prepared_args = prepare_tool_arguments(tool_name, tool_args, state_updates)

            logger.info("\n📞 CALLING TOOL FUNCTION...")
            logger.info(f"📨 Prepared Arguments: {json.dumps(prepared_args, indent=2)}")

            # Execute the tool
            output = tool_to_call.invoke(prepared_args)
            logger.info(f"\n✅ Tool execution completed")

            # Check if execution was successful
            if output.get("status") in ["success", "partial_success"]:
                execution_successful = True

            # Update state based on tool output
            update_state_from_tool_output(tool_name, output, prepared_args, state_updates)

            # Format output for LLM
            if tool_name == "create_trip_and_check_availability":
                if output.get("status") == "success":
                    # Reset error count on success
                    state_updates["error_count"] = 0
                    state_updates["last_error_type"] = ""

                    output_str = json.dumps({
                        "status": "success",
                        "message": "SUCCESS: I'm connecting with drivers for prices and availability. You'll start receiving driver details with prices shortly. This may take a few minutes.",
                        "trip_id": output.get("trip_id"),
                        "booking_confirmed": True,
                        "note": "DO NOT mention driver count to user"
                    })
                    logger.info(f"✅ Trip {output.get('trip_id')} - {output.get('drivers_notified')} drivers notified")

                elif output.get("status") == "partial_success":
                    # Increment error count for partial success
                    current_error = state_updates.get("error_count", 0)

                    output_str = json.dumps({
                        "status": "partial_success",
                        "message": output.get("message"),
                        "trip_id": output.get("trip_id"),
                        "suggestion": "Try with fewer filters or different preferences" if current_error > 1 else None,
                        "support_last_resort": "If issues persist, call +919403892230" if current_error > 2 else None
                    })

                    state_updates["error_count"] = current_error + 1
                    state_updates["last_error_type"] = "no_drivers"

                else:
                    # Error status
                    current_error = state_updates.get("error_count", 0) + 1
                    state_updates["error_count"] = current_error
                    state_updates["last_error_type"] = "api_error"

                    if current_error > 3:
                        output_str = json.dumps({
                            "status": "error",
                            "message": "Multiple attempts failed. Support: +919403892230"
                        })
                    else:
                        output_str = json.dumps({
                            "status": "error",
                            "message": "Let me try a different approach",
                            "retry_attempt": current_error
                        })
            else:
                output_str = json.dumps(output) if isinstance(output, dict) else str(output)

            tool_messages.append(
                ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
            )

        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_name}: {e}", exc_info=True)

            # Increment error count
            current_error = state_updates.get("error_count", 0) + 1
            state_updates["error_count"] = current_error
            state_updates["last_error_type"] = "tool_execution_error"

            if current_error > 3:
                error_msg = json.dumps({
                    "status": "error",
                    "message": "Technical issues persist. Support: +919403892230"
                })
            else:
                error_msg = json.dumps({
                    "status": "error",
                    "message": f"Technical issue (attempt {current_error}). Trying alternative approach..."
                })

            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )

    # Update the chat history
    state_updates["chat_history"] = state.get("chat_history", []) + tool_messages
    state_updates["tool_calls"] = []

    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR COMPLETED")
    logger.info(f"Execution successful: {execution_successful}")
    logger.info(f"Error count: {state_updates.get('error_count', 0)}")
    logger.info("="*50)

    return state_updates


def prepare_tool_arguments(tool_name: str, tool_args: Dict[str, Any], state: dict) -> Dict[str, Any]:
    """
    Prepare tool arguments, ensuring proper format for API.
    Enhanced with intelligent filter mapping.
    """
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

                # Handle pagination
                if "page" not in args:
                    current_page = state.get("current_page", 1)
                    args["page"] = current_page + 1
                    logger.info(f"  📖 Auto-incrementing page: {current_page} → {args['page']}")

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

        # Ensure filters are in correct API format
        if "filters" in args:
            args["filters"] = ensure_api_filter_format(args["filters"])
            logger.info(f"  🎯 API-formatted filters: {args['filters']}")

    return args


def ensure_api_filter_format(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced filter formatting with complete preference mapping.
    Handles all special service requests intelligently.
    """
    if not filters:
        return {}

    api_filters = {}

    # Copy over filters, ensuring correct format
    for key, value in filters.items():
        # Skip internal flags
        if key in ['auto_inferred', 'passenger_count', 'explicit_vehicle',
                   'request_more_drivers', 'fetch_more_drivers', 'has_budget_concern']:
            continue

        # Ensure vehicles is comma-separated string
        if key in ["vehicles", "vehicleTypes"]:
            if isinstance(value, list):
                api_filters["vehicles"] = ','.join(value)
            else:
                api_filters["vehicles"] = str(value)

        # Handle all boolean filters for special services
        elif key in ['isPetAllowed', 'married', 'verified', 'profileVerified',
                     'allowHandicappedPersons', 'availableForCustomersPersonalCar',
                     'availableForDrivingInEventWedding', 'availableForPartTimeFullTime']:
            if isinstance(value, bool):
                api_filters[key] = "true" if value else "false"
            elif isinstance(value, str) and value.lower() in ["true", "false"]:
                api_filters[key] = value.lower()
            else:
                api_filters[key] = "true" if value else "false"

        # Ensure integers are integers
        elif key in ['minDrivingExperience', 'minAge', 'maxAge', 'minConnections']:
            try:
                api_filters[key] = int(value)
            except (ValueError, TypeError):
                logger.warning(f"Could not convert {key}={value} to integer, skipping")

        # Handle gender filter
        elif key == 'gender':
            if value and value.lower() in ['male', 'female']:
                api_filters['gender'] = value.lower()

        # Handle language filter
        elif key == 'language':
            api_filters['language'] = str(value)

        # Pass through other filters as-is
        else:
            api_filters[key] = value

    return api_filters


def update_state_from_tool_output(
    tool_name: str,
    output: Any,
    tool_args: Dict[str, Any],
    state: dict
) -> None:
    """Update state based on tool output"""
    logger.info("\nUpdating state from tool output...")

    if tool_name == "create_trip_and_check_availability":
        if output.get("status") in ["success", "partial_success"]:
            # Store trip details
            if output.get("trip_id"):
                state["trip_id"] = output.get("trip_id")
                state["pickup_location"] = tool_args.get("pickup_city")
                state["drop_location"] = tool_args.get("drop_city")
                state["trip_type"] = tool_args.get("trip_type")
                state["start_date"] = tool_args.get("start_date")
                state["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")

            # Update filters and status
            state["applied_filters"] = tool_args.get("filters", {})
            state["booking_status"] = "completed" if output.get("status") == "success" else "partial"

            # Update pagination
            if tool_args.get("fetch_more_drivers"):
                page_used = tool_args.get("page", 1)
                state["current_page"] = page_used
                logger.info(f"  📖 Updated current page to: {page_used}")
            else:
                state["current_page"] = 1

            # Track notified drivers
            new_driver_ids = output.get("driver_ids", [])
            if tool_args.get("fetch_more_drivers"):
                existing_ids = state.get("driver_ids_notified", [])
                state["driver_ids_notified"] = existing_ids + new_driver_ids
            else:
                state["driver_ids_notified"] = new_driver_ids

            logger.info("  ✅ State Updated:")
            logger.info(f"     - Trip ID: {state.get('trip_id')}")
            logger.info(f"     - Current Page: {state.get('current_page')}")
            logger.info(f"     - Total Drivers Notified: {len(state.get('driver_ids_notified', []))}")
            logger.info(f"     - Booking Status: {state.get('booking_status')}")
            logger.info(f"     - Error Count: {state.get('error_count', 0)}")
