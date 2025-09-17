# langgraph_agent/graph/nodes.py
"""Simplified LLM-driven agent - trusting LLM's intelligence"""

import json
import logging
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI

from langgraph_agent.graph.sys_prompt import bot_prompt
from langgraph_agent.tools.drivers_tools import create_trip_with_preferences, cancel_trip

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tools list
tools = [create_trip_with_preferences, cancel_trip]

# Initialize LLM
llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.7)
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplified agent node - trusting LLM to extract everything intelligently.
    """
    logger.info("\n" + "="*50)
    logger.info("AGENT NODE EXECUTION")
    logger.info("="*50)

    # Log current state
    logger.info("Current State:")
    logger.info(f"  - Customer ID: {state.get('customer_id')}")
    logger.info(f"  - Trip ID: {state.get('trip_id')}")
    logger.info(f"  - Source: {state.get('source', 'app')}")

    # Get current date for context
    current_date_str = datetime.now().strftime("%Y-%m-%d")

    # Get chat history
    chat_history = state.get("chat_history", [])

    # Build enhanced prompt with FAQ knowledge and current state
    enhanced_prompt = bot_prompt.replace("{current_date}", current_date_str) + f"""

## CURRENT STATE:
- Trip ID: {state.get('trip_id', 'None')}
- Source: {state.get('source', 'app')}
- Customer: {state.get('customer_name', 'Unknown')} (ID: {state.get('customer_id', 'None')})

## INSTRUCTIONS:
1. If user asks about CabsWale (pricing, safety, how it works, etc.) - answer from the FAQ knowledge
2. If user wants to book - extract ALL details intelligently (cities, date, passengers, preferences)
3. If user wants to cancel and trip exists - cancel it
4. Trust your intelligence to extract passenger count from ANY language/format
5. Auto-select vehicle based on passenger count (8+ → TempoTraveller, 5-7 → SUV)
6. Never mention unsupported preferences to users

Be natural and conversational. You're smart enough to understand context in any language!
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
                # Direct response (could be FAQ or asking for more info)
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

        error_message = "I encountered an issue. You can call our support at +919403892230 for immediate assistance, or try again with your booking request."

        return {
            **state,
            "last_bot_response": error_message,
            "tool_calls": []
        }


def tool_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tools for trip creation or cancellation"""
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
            if tool_name == "cancel_trip":
                # Handle trip cancellation
                tool_args["customer_id"] = state_updates.get("customer_id") or ""

                logger.info("\n📞 CALLING CANCELLATION TOOL...")
                output = tool_to_call.invoke(tool_args)

                if output.get("status") == "success":
                    state_updates["trip_id"] = None
                    state_updates["booking_status"] = "cancelled"

                output_str = json.dumps(output)

            else:  # create_trip_with_preferences
                # Add customer details
                tool_args["customer_details"] = {
                    "id": state_updates.get("customer_id") or "",
                    "name": state_updates.get("customer_name") or "",
                    "phone": state_updates.get("customer_phone") or "",
                    "profile_image": state_updates.get("customer_profile") or "",
                }

                # Add source
                tool_args["source"] = state_updates.get("source", "app")

                # The LLM should have extracted passenger_count if mentioned
                # It's passed in tool_args directly by the LLM

                logger.info("\n📞 CALLING TRIP CREATION TOOL...")

                # Execute the tool
                output = tool_to_call.invoke(tool_args)
                logger.info(f"\n✅ Tool execution completed")

                # Update state based on tool output
                if output.get("status") == "success":
                    state_updates["trip_id"] = output.get("trip_id")
                    state_updates["booking_status"] = "completed"

                    # Store trip details from tool args
                    state_updates["pickup_location"] = tool_args.get("pickup_city")
                    state_updates["drop_location"] = tool_args.get("drop_city")
                    state_updates["trip_type"] = tool_args.get("trip_type")
                    state_updates["start_date"] = tool_args.get("start_date")
                    state_updates["end_date"] = tool_args.get("return_date") or tool_args.get("start_date")
                    state_updates["user_preferences"] = tool_args.get("preferences", {})

                    # Store passenger count if it was provided
                    if tool_args.get("passenger_count"):
                        state_updates["passenger_count"] = tool_args.get("passenger_count")

                    output_str = json.dumps({
                        "status": "success",
                        "message": output.get("message"),
                        "trip_id": output.get("trip_id")
                    })

                    logger.info(f"✅ Trip {output.get('trip_id')} created successfully")
                else:
                    output_str = json.dumps({
                        "status": "error",
                        "message": output.get("message", "Failed to create trip. Please try again or call support at +919403892230.")
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
