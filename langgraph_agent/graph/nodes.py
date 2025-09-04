# langgraph_agent/graph/nodes.py
"""LLM-driven intelligent agent with full multilingual support"""

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
    No hardcoded checks - everything is handled by the LLM.
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

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

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

## YOUR TASK:
Analyze the user's message and determine the appropriate response. Consider:

1. **Language**: Respond in the same language as the user (Hindi, Punjabi, English, etc.)

2. **Intent Detection**: Understand what the user wants:
   - Booking a cab (customer) vs. Looking for duty (driver/partner)
   - Price negotiation or budget concerns
   - Questions about tolls/taxes/charges
   - Requesting more drivers
   - General queries or clarifications
   - Ambiguous responses like "no" (understand from context)

3. **Information Extraction**: Extract from ANY language:
   - Cities (pickup and drop)
   - Dates and times
   - Trip type (one-way/round-trip)
   - Number of passengers
   - Vehicle preferences
   - Driver preferences (language, experience, etc.)

4. **Smart Defaults**:
   - 9+ passengers → Auto-select 12-seater Tempo Traveller
   - 5-8 passengers → Auto-select SUV
   - Don't auto-select for budget mentions

5. **State Management**:
   - If trip details change → Create new trip
   - If only requesting more drivers → Reuse trip, increment page

6. **Tool Calling Rules**:
   - ONLY call tool when ALL trip details are available
   - Convert filters to API format properly:
     * vehicleTypes → vehicles (comma-separated string)
     * Language preference → language (single value)
     * Booleans → "true"/"false" strings
     * Experience → minDrivingExperience (integer)
   - Page management: current page is {state.get('current_page', 1)}, next would be {state.get('current_page', 1) + 1}

7. **Response Templates** (adapt to user's language):
   - Price/Budget → Negotiation template with support number
   - Tolls/Taxes → Inclusive pricing explanation
   - Errors → Include support number +919403892230
   - Success → Don't mention driver count

Remember: You understand ALL languages. Extract information regardless of language.
Respond naturally in the user's language. Be helpful and efficient.
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
                # Direct response
                logger.info("✅ Agent provided direct response")

                # The LLM might have updated our understanding - let's parse it
                response_content = ai_response.content

                # Update state if LLM extracted any information
                # The LLM will tell us what it extracted in its response
                state_updates = extract_state_updates_from_llm_response(response_content, state)

                return {
                    **state,
                    **state_updates,
                    "chat_history": updated_history,
                    "last_bot_response": response_content,
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
        # Let LLM handle error message in user's language
        error_prompt = f"""
        There was a technical error. Please provide an appropriate error message in the user's language.
        Include the support number +919403892230 for assistance.
        Be apologetic and helpful.
        """

        try:
            error_response = llm.invoke([SystemMessage(content=error_prompt)] + chat_history[-1:])
            error_message = error_response.content
        except:
            error_message = "I apologize, but I encountered an issue. Please call CabsWale Support at +919403892230 for immediate assistance."

        return {
            **state,
            "last_bot_response": error_message,
            "tool_calls": [],
        }


def extract_state_updates_from_llm_response(response: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract any state updates that the LLM might have identified.
    This is a helper function that can parse LLM responses for state changes.
    """
    updates = {}

    # The LLM might indicate extracted information in its response
    # We can add patterns here if needed, but primarily we rely on
    # the LLM to call tools when it has all information

    # For now, return empty updates as the LLM handles everything
    return updates


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
        logger.info(f"📋 Tool Arguments from LLM: {json.dumps(tool_args, indent=2)}")

        tool_to_call = tool_map.get(tool_name)
        if not tool_to_call:
            error_msg = f"Tool '{tool_name}' not found. Please contact support at +919403892230."
            logger.error(f"❌ {error_msg}")
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )
            continue

        try:
            # Prepare tool arguments
            prepared_args = prepare_tool_arguments(tool_name, tool_args, state_updates)

            logger.info("\n📞 CALLING TOOL FUNCTION...")
            logger.info(f"📨 Prepared Arguments: {json.dumps(prepared_args, indent=2)}")

            # Execute the tool
            output = tool_to_call.invoke(prepared_args)
            logger.info(f"\n✅ Tool execution completed")

            # Update state based on tool output
            update_state_from_tool_output(tool_name, output, prepared_args, state_updates)

            # Format output for LLM
            if tool_name == "create_trip_and_check_availability":
                if output.get("status") == "success":
                    # Success message that LLM will convert to user's language
                    output_str = json.dumps({
                        "status": "success",
                        "message": "SUCCESS: I'm connecting with drivers for prices and availability. You'll start receiving driver details with prices shortly. This may take a few minutes.",
                        "trip_id": output.get("trip_id"),
                        "booking_confirmed": True,
                        "note": "DO NOT mention driver count to user"
                    })
                    logger.info(f"✅ Trip {output.get('trip_id')} - {output.get('drivers_notified')} drivers notified")
                elif output.get("status") == "partial_success":
                    output_str = json.dumps({
                        "status": "partial_success",
                        "message": output.get("message"),
                        "trip_id": output.get("trip_id"),
                        "support_required": "If I'm unable to assist, please call CabsWale Support for immediate help on +919403892230"
                    })
                else:
                    output_str = json.dumps({
                        "status": "error",
                        "message": output.get("message", "Technical error occurred"),
                        "support": "If I'm unable to assist, please call CabsWale Support for immediate help on +919403892230"
                    })
            else:
                output_str = json.dumps(output) if isinstance(output, dict) else str(output)

            tool_messages.append(
                ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
            )

        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_name}: {e}", exc_info=True)
            error_msg = json.dumps({
                "status": "error",
                "message": "Technical error occurred. Support: +919403892230"
            })
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )

    # Update the chat history
    state_updates["chat_history"] = state.get("chat_history", []) + tool_messages
    state_updates["tool_calls"] = []

    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR COMPLETED")
    logger.info("="*50)

    return state_updates


def prepare_tool_arguments(tool_name: str, tool_args: Dict[str, Any], state: dict) -> Dict[str, Any]:
    """
    Prepare tool arguments, ensuring proper format for API.
    The LLM provides the arguments, we just ensure they're in the right format.
    """
    logger.info("\n🔧 Preparing tool arguments...")
    args = tool_args.copy()

    if tool_name == "create_trip_and_check_availability":
        # Check if we should reuse existing trip
        if state.get("trip_id") and state.get("booking_status") == "completed":
            # Check if core trip details match (LLM should handle this, but double-check)
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
    Ensure filters are in the correct format for the API.
    The LLM should provide these correctly, but we validate here.
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
        if key == "vehicles":
            if isinstance(value, list):
                api_filters["vehicles"] = ','.join(value)
            else:
                api_filters["vehicles"] = str(value)

        # Ensure booleans are strings
        elif key in ['isPetAllowed', 'married', 'verified', 'profileVerified',
                     'allowHandicappedPersons', 'availableForCustomersPersonalCar',
                     'availableForDrivingInEventWedding', 'availableForPartTimeFullTime']:
            if isinstance(value, bool):
                api_filters[key] = "true" if value else "false"
            elif isinstance(value, str) and value in ["true", "false"]:
                api_filters[key] = value
            else:
                api_filters[key] = "true" if value else "false"

        # Ensure integers are integers
        elif key in ['minDrivingExperience', 'minAge', 'maxAge', 'minConnections']:
            try:
                api_filters[key] = int(value)
            except (ValueError, TypeError):
                logger.warning(f"Could not convert {key}={value} to integer, skipping")

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
