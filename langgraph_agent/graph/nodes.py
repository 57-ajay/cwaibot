# langgraph_agent/graph/nodes.py
"""Clean and optimized LLM-driven agent nodes with trip modification support"""

import json
import logging
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI

from langgraph_agent.graph.sys_prompt import bot_prompt
from langgraph_agent.tools.drivers_tools import create_trip_with_preferences, cancel_trip, handle_trip_modification

# Minimal logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Only warnings and errors

# Tools list - now includes modification handler
tools = [create_trip_with_preferences, cancel_trip, handle_trip_modification]

# Initialize LLM
llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.7)
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplified agent node - trusting LLM to handle modifications intelligently.
    """
    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Build enhanced prompt with current state and existing trip details
    existing_trip_info = ""
    if state.get('trip_id'):
        existing_trip_info = f"""
## EXISTING TRIP DETAILS:
- Trip ID: {state.get('trip_id')}
- Route: {state.get('pickup_location', 'Unknown')} to {state.get('drop_location', 'Unknown')}
- Date: {state.get('start_date', 'Not set')}
- Trip Type: {state.get('trip_type', 'Not set')}
- Return Date: {state.get('end_date', 'N/A')}
- Preferences: {json.dumps(state.get('user_preferences', {}))}
- Passenger Count: {state.get('passenger_count', 1)}

IMPORTANT: If user wants to modify preferences, date, or trip type for THIS trip → Use handle_trip_modification tool
If user wants a NEW trip with different pickup/drop → Just create new trip
"""

    enhanced_prompt = bot_prompt.replace("{current_date}", current_date_str) + f"""

## CURRENT STATE:
- Customer: {state.get('customer_name', 'Unknown')} (ID: {state.get('customer_id', 'None')})
- Source: {state.get('source', 'app')}
{existing_trip_info}

## MODIFICATION INSTRUCTIONS:
1. If user wants to MODIFY existing trip (change preferences/date/tripType) → Use handle_trip_modification tool
2. If user wants NEW trip with different route → Use create_trip_with_preferences
3. If user explicitly asks to CANCEL → Use cancel_trip
4. Extract preferences EXACTLY in the supported format
5. Pass empty object {{}} for preferences if none mentioned

## TOOL SELECTION LOGIC:
- User changes preferences/date/tripType for existing trip → handle_trip_modification
- User wants trip with different pickup/drop → create_trip_with_preferences
- User says "cancel" explicitly → cancel_trip
- First trip creation → create_trip_with_preferences
"""

    # Build messages for LLM
    messages = [SystemMessage(content=enhanced_prompt)]
    if chat_history:
        messages.extend(chat_history)

    # Get LLM response
    try:
        ai_response = llm_with_tools.invoke(messages)

        # Update chat history
        updated_history = chat_history + [ai_response]

        # Check if the response has tool_calls
        if isinstance(ai_response, AIMessage):
            if not ai_response.tool_calls:
                # Direct response (FAQ or asking for more info)
                return {
                    **state,
                    "chat_history": updated_history,
                    "last_bot_response": ai_response.content,
                    "tool_calls": []
                }
            else:
                # Agent wants to call tools
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
                "tool_calls": []
            }

    except Exception as e:
        logger.error(f"Error in agent_node: {e}")

        error_message = "I encountered an issue. You can call our support at +919403892230 for immediate assistance."

        return {
            **state,
            "last_bot_response": error_message,
            "tool_calls": []
        }


def tool_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tools for trip creation, modification, or cancellation"""

    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return state

    tool_map = {tool.name: tool for tool in tools}
    tool_messages = []
    state_updates = dict(state)

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")

        tool_to_call = tool_map.get(tool_name)
        if not tool_to_call:
            error_msg = f"Tool '{tool_name}' not found."
            logger.error(error_msg)
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )
            continue

        try:
            if tool_name == "cancel_trip":
                # Handle trip cancellation
                tool_args["customer_id"] = state_updates.get("customer_id") or ""

                output = tool_to_call.invoke(tool_args)

                if output.get("status") == "success":
                    state_updates["trip_id"] = None
                    state_updates["booking_status"] = "cancelled"
                    # Clear trip details
                    state_updates["pickup_location"] = None
                    state_updates["drop_location"] = None
                    state_updates["trip_type"] = None
                    state_updates["start_date"] = None
                    state_updates["end_date"] = None
                    state_updates["user_preferences"] = {}
                    state_updates["passenger_count"] = None

                output_str = json.dumps(output)

            elif tool_name == "handle_trip_modification":
                # Handle trip modification (cancel + create new)
                # Add existing state details to tool args
                tool_args["existing_trip_id"] = state_updates.get("trip_id")
                tool_args["existing_pickup"] = state_updates.get("pickup_location")
                tool_args["existing_drop"] = state_updates.get("drop_location")
                tool_args["existing_trip_type"] = state_updates.get("trip_type")
                tool_args["existing_start_date"] = state_updates.get("start_date")
                tool_args["existing_end_date"] = state_updates.get("end_date")
                tool_args["existing_preferences"] = state_updates.get("user_preferences", {})
                tool_args["existing_passenger_count"] = state_updates.get("passenger_count")

                # Add customer details
                tool_args["customer_details"] = {
                    "id": state_updates.get("customer_id") or "",
                    "name": state_updates.get("customer_name") or "",
                    "phone": state_updates.get("customer_phone") or "",
                    "profile_image": state_updates.get("customer_profile") or "",
                }

                # Add source and location objects
                tool_args["source"] = state_updates.get("source", "None")
                if state_updates.get("pickup_location_object"):
                    tool_args["pickup_location_object"] = state_updates["pickup_location_object"]
                if state_updates.get("drop_location_object"):
                    tool_args["drop_location_object"] = state_updates["drop_location_object"]

                # Execute the modification
                output = tool_to_call.invoke(tool_args)

                # Update state with new trip details
                if output.get("status") == "success":
                    state_updates["trip_id"] = output.get("new_trip_id")
                    state_updates["booking_status"] = "modified"

                    # Update with new details from tool_args
                    if tool_args.get("new_pickup"):
                        state_updates["pickup_location"] = tool_args["new_pickup"]
                    if tool_args.get("new_drop"):
                        state_updates["drop_location"] = tool_args["new_drop"]
                    if tool_args.get("new_trip_type"):
                        state_updates["trip_type"] = tool_args["new_trip_type"]
                    if tool_args.get("new_start_date"):
                        state_updates["start_date"] = tool_args["new_start_date"]
                    if tool_args.get("new_end_date"):
                        state_updates["end_date"] = tool_args["new_end_date"]
                    if tool_args.get("new_preferences"):
                        # Merge preferences
                        state_updates["user_preferences"] = {
                            **state_updates.get("user_preferences", {}),
                            **tool_args["new_preferences"]
                        }
                    if tool_args.get("new_passenger_count"):
                        state_updates["passenger_count"] = tool_args["new_passenger_count"]

                    output_str = json.dumps({
                        "status": "success",
                        "message": output.get("message"),
                        "new_trip_id": output.get("new_trip_id")
                    })

                    logger.info(f"Trip modified: Old {output.get('old_trip_id')} → New {output.get('new_trip_id')}")
                else:
                    output_str = json.dumps({
                        "status": "error",
                        "message": output.get("message", "Failed to modify trip. Please try again or call support.")
                    })

            else:  # create_trip_with_preferences
                # Add customer details
                tool_args["customer_details"] = {
                    "id": state_updates.get("customer_id") or "",
                    "name": state_updates.get("customer_name") or "",
                    "phone": state_updates.get("customer_phone") or "",
                    "profile_image": state_updates.get("customer_profile") or "",
                }

                # Add source
                tool_args["source"] = state_updates.get("source", "None")

                # Add location objects if available
                if state_updates.get("pickup_location_object"):
                    tool_args["pickup_location_object"] = state_updates["pickup_location_object"]
                if state_updates.get("drop_location_object"):
                    tool_args["drop_location_object"] = state_updates["drop_location_object"]

                # Execute the tool
                output = tool_to_call.invoke(tool_args)

                # Update state based on tool output
                if output.get("status") == "success":
                    state_updates["trip_id"] = output.get("trip_id")
                    state_updates["booking_status"] = "completed"

                    # Store trip details
                    state_updates["pickup_location"] = tool_args.get("pickup_city")
                    state_updates["drop_location"] = tool_args.get("drop_city")
                    state_updates["trip_type"] = tool_args.get("trip_type")
                    state_updates["start_date"] = tool_args.get("start_date")
                    state_updates["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")
                    state_updates["user_preferences"] = tool_args.get("preferences", {})

                    if tool_args.get("passenger_count"):
                        state_updates["passenger_count"] = tool_args.get("passenger_count")

                    output_str = json.dumps({
                        "status": "success",
                        "message": output.get("message"),
                        "trip_id": output.get("trip_id")
                    })

                    logger.info(f"Trip {output.get('trip_id')} created successfully")
                else:
                    output_str = json.dumps({
                        "status": "error",
                        "message": output.get("message", "Failed to create trip. Please try again or call support at +919403892230.")
                    })

            tool_messages.append(
                ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")

            error_msg = json.dumps({
                "status": "error",
                "message": "Technical issue occurred. Please try again or call support at +919403892230"
            })

            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )

    # Update the chat history
    state_updates["chat_history"] = state.get("chat_history", []) + tool_messages
    state_updates["tool_calls"] = []

    return state_updates
