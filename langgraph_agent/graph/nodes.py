# langgraph_agent/graph/nodes.py
"""Simplified LLM-driven agent focused on trip creation with preferences"""

import json
import logging
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI

from langgraph_agent.graph.sys_prompt import bot_prompt
from langgraph_agent.tools.drivers_tools import create_trip_with_preferences

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tools list - simplified to just trip creation
tools = [create_trip_with_preferences]

# Initialize LLM
llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.7)
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplified agent node focused on trip creation.
    Collects trip details and preferences, then creates the trip.
    """
    logger.info("\n" + "="*50)
    logger.info("AGENT NODE EXECUTION")
    logger.info("="*50)

    # Log current state
    logger.info("Current State:")
    logger.info(f"  - Customer ID: {state.get('customer_id')}")
    logger.info(f"  - Trip ID: {state.get('trip_id')}")
    logger.info(f"  - Route: {state.get('pickup_location')} to {state.get('drop_location')}")
    logger.info(f"  - Preferences: {state.get('user_preferences', {})}")

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Build simplified prompt - use f-string for the entire prompt
    enhanced_prompt = bot_prompt.replace("{current_date}", current_date_str) + f"""

## CURRENT CONVERSATION STATE:
- Pickup Location: {state.get('pickup_location', 'Not set')}
- Drop Location: {state.get('drop_location', 'Not set')}
- Travel Date: {state.get('start_date', 'Not set')}
- Trip Type: {state.get('trip_type', 'Not set')}
- User Preferences: {json.dumps(state.get('user_preferences', {}))}
- Trip ID: {state.get('trip_id', 'None')}

## YOUR TASK:
1. Collect ALL trip details: pickup city, drop city, travel date, trip type (one-way/round-trip)
2. Ask for user preferences (vehicle type, driver preferences, etc.) - but ONLY if not already provided
3. Once you have ALL information, create the trip with preferences
4. NEVER create a trip with partial information
5. Be conversational and minimize questions - if user provides everything, don't ask again

Remember: Your ONLY job is to collect information and create the trip. Firebase will handle driver notifications automatically.
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
                    "tool_calls": []
                }
            else:
                # Agent wants to call tools
                logger.info(f"🔧 Agent requesting tool call")
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
                "tool_calls": []
            }

    except Exception as e:
        logger.error(f"❌ Error in agent_node: {e}", exc_info=True)

        error_message = "I encountered an issue. Let me help you book your cab. Please provide your pickup city, destination, and travel date."

        return {
            **state,
            "last_bot_response": error_message,
            "tool_calls": []
        }


def tool_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tool to create trip with preferences"""
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
        logger.info(f"📋 Tool Arguments: {json.dumps(tool_args, indent=2)}")

        tool_to_call = tool_map.get(tool_name)
        if not tool_to_call:
            error_msg = f"Tool '{tool_name}' not found."
            logger.error(f"❌ {error_msg}")
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id, name=tool_name)
            )
            continue

        try:
            # Add customer details - use empty strings if missing
            tool_args["customer_details"] = {
                "id": state_updates.get("customer_id") or "",
                "name": state_updates.get("customer_name") or "",
                "phone": state_updates.get("customer_phone") or "",
                "profile_image": state_updates.get("customer_profile") or "",
            }

            logger.info("\n📞 CALLING TOOL FUNCTION...")

            # Execute the tool
            output = tool_to_call.invoke(tool_args)
            logger.info(f"\n✅ Tool execution completed")

            # Update state based on tool output
            if output.get("status") == "success":
                state_updates["trip_id"] = output.get("trip_id")
                state_updates["booking_status"] = "completed"
                state_updates["pickup_location"] = tool_args.get("pickup_city")
                state_updates["drop_location"] = tool_args.get("drop_city")
                state_updates["trip_type"] = tool_args.get("trip_type")
                state_updates["start_date"] = tool_args.get("start_date")
                state_updates["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")
                state_updates["user_preferences"] = tool_args.get("preferences", {})

                output_str = json.dumps({
                    "status": "success",
                    "message": output.get("message"),
                    "trip_id": output.get("trip_id")
                })

                logger.info(f"✅ Trip {output.get('trip_id')} created successfully")
            else:
                output_str = json.dumps({
                    "status": "error",
                    "message": output.get("message", "Failed to create trip. Please try again.")
                })

            tool_messages.append(
                ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
            )

        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_name}: {e}", exc_info=True)

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

    logger.info("\n" + "="*50)
    logger.info("TOOL EXECUTOR COMPLETED")
    logger.info("="*50)

    return state_updates
