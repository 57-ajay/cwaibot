# langgraph_agent/graph/builder.py
"""Enhanced LangGraph agent builder with new features"""

from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage


# Define the enhanced state type
class GraphState(TypedDict, total=False):
    """Enhanced state definition for the graph"""
    chat_history: List[BaseMessage]
    user_preferences: Dict[str, Any]
    trip_id: Optional[str]
    pickup_location: Optional[str]
    drop_location: Optional[str]
    trip_type: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    customer_id: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    customer_profile: Optional[str]
    last_bot_response: Optional[str]
    tool_calls: List[Dict[str, Any]]
    booking_status: Optional[str]
    # New fields
    source: Optional[str]  # Source of booking: 'app', 'website', 'whatsapp'
    passenger_count: Optional[int]  # Number of passengers for smart vehicle selection


# Import and wrap node functions
from langgraph_agent.graph import nodes


def agent_node_wrapper(state: GraphState) -> Dict[str, Any]:
    """Agent node wrapper with proper typing"""
    return nodes.agent_node(dict(state))


def tool_executor_node_wrapper(state: GraphState) -> Dict[str, Any]:
    """Tool executor node wrapper with proper typing"""
    return nodes.tool_executor_node(dict(state))


def route_after_agent(state: GraphState) -> str:
    """Router to decide next step after agent"""
    if state.get("tool_calls"):
        return "action"
    else:
        return END


def create_graph():
    """Create the enhanced LangGraph workflow"""
    workflow = StateGraph(GraphState)

    # Add nodes with wrapped functions
    workflow.add_node("agent", agent_node_wrapper)
    workflow.add_node("action", tool_executor_node_wrapper)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {"action": "action", END: END}
    )

    # After tools, go back to agent
    workflow.add_edge("action", "agent")

    return workflow.compile()


# Create the app
app = create_graph()
