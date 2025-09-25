# langgraph_agent/tools/drivers_tools.py
"""Clean and optimized driver tools with proper preference handling"""

import logging
from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
from datetime import datetime, timezone
from services import api_client

# Minimal logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


@tool
def cancel_trip(
    trip_id: str,
    customer_id: str
) -> Dict[str, Any]:
    """
    Cancels an existing trip.

    Args:
        trip_id: The ID of the trip to cancel
        customer_id: The customer ID for verification

    Returns:
        Dictionary with cancellation status
    """
    try:
        result = api_client.cancel_trip(trip_id)

        if result and result.get("status") == "success":
            logger.info(f"Trip {trip_id} cancelled")
            return {
                "status": "success",
                "message": f"Your trip has been cancelled successfully. Trip ID: {trip_id}"
            }
        else:
            return {
                "status": "error",
                "message": "Unable to cancel the trip. Please try again or contact support at +919403892230"
            }

    except Exception as e:
        logger.error(f"Error cancelling trip: {e}")
        return {
            "status": "error",
            "message": "Technical issue occurred while cancelling. Please contact support at +919403892230"
        }


@tool
def create_trip_with_preferences(
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    customer_details: Dict[str, str],
    start_date: str,
    return_date: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    source: Optional[str] = "None",
    passenger_count: Optional[int] = None,
    pickup_location_object: Optional[Dict[str, Any]] = None,
    drop_location_object: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Creates a trip with user preferences and smart vehicle selection.

    Args:
        pickup_city: The city from where the trip starts
        drop_city: The city where the trip ends
        trip_type: The type of trip, must be either 'one-way' or 'round-trip'
        customer_details: Dictionary containing customer's id, name, phone, and profile_image
        start_date: The start date for the trip, in YYYY-MM-DD format
        return_date: (Optional) The return date for a round-trip, in YYYY-MM-DD format
        preferences: (Optional) User preferences for the trip with exact format
        source: (Optional) Source of the booking - 'app', 'website', or 'whatsapp'
        passenger_count: (Optional) Number of passengers for smart vehicle selection

    Returns:
        Dictionary with trip creation status
    """
    # Format dates for API
    def format_date_for_api(date_str):
        """Convert YYYY-MM-DD to ISO format with current time"""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            current_time = datetime.now(timezone.utc)
            dt_with_time = datetime(
                dt.year, dt.month, dt.day,
                current_time.hour, current_time.minute, current_time.second,
                tzinfo=timezone.utc
            )
            return dt_with_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        except (ValueError, TypeError):
            return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    formatted_start_date = format_date_for_api(start_date)

    if trip_type.lower() == "round-trip":
        if not return_date:
            return {
                "status": "error",
                "message": "Return date is required for a round-trip."
            }
        formatted_end_date = format_date_for_api(return_date)
    else:
        formatted_end_date = formatted_start_date

    # Process preferences with smart vehicle selection
    processed_preferences = process_preferences(preferences, passenger_count)

    # Call trip creation API
    trip_data = api_client.create_trip_with_preferences(
        customer_details,
        pickup_city,
        drop_city,
        trip_type.lower(),
        formatted_start_date,
        formatted_end_date,
        processed_preferences,
        source,
        pickup_location_object,
        drop_location_object
    )

    if not trip_data or "tripId" not in trip_data:
        return {
            "status": "error",
            "message": "Failed to create the trip. Please try again."
        }

    trip_id = trip_data.get("tripId")
    logger.info(f"Trip created: {trip_id}")

    # Return with the exact success message
    return {
        "status": "success",
        "message": "**Great! We're reaching out to drivers for you.**\n\nYou'll start getting quotes in just a few minutes.",
        "trip_id": trip_id
    }


def process_preferences(
    preferences: Optional[Dict[str, Any]],
    passenger_count: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process user preferences with exact format required by API.

    Expected preference format:
    {
        "gender": "male" / "female",
        "dlDateOfIssue": "asc" / "desc",
        "languages": ["English", "Hindi"],
        "vehicleTypesList": ["sedan", "suv"],
        "isPetAllowed": true/false,
        "allowHandicappedPersons": true/false,
        "married": true/false,
        "availableForCustomersPersonalCar": true/false,
        "availableForDrivingInEventWedding": true/false,
        "availableForPartTimeFullTime": true/false,
        "connections": "asc" / "desc",
        "age": 40  // maximum age
    }
    """
    if not preferences:
        preferences = {}

    processed = {}

    # Smart vehicle selection based on passenger count
    if passenger_count:
        if passenger_count >= 8:
            # Ensure Tempo Traveller for large groups
            if "vehicleTypesList" in preferences:
                if "tempotraveller" not in preferences["vehicleTypesList"]:
                    preferences["vehicleTypesList"].append("tempotraveller")
            else:
                preferences["vehicleTypesList"] = ["tempotraveller"]

        elif passenger_count >= 5:
            # Ensure SUV for medium groups
            if "vehicleTypesList" in preferences:
                if "suv" not in preferences["vehicleTypesList"]:
                    preferences["vehicleTypesList"].append("suv")
            else:
                preferences["vehicleTypesList"] = ["suv"]

    # Process each preference field with exact format

    # Gender preference - string
    if "gender" in preferences and preferences["gender"] in ["male", "female"]:
        processed["gender"] = preferences["gender"]

    # License date of issue (experience) - string
    if "dlDateOfIssue" in preferences and preferences["dlDateOfIssue"] in ["asc", "desc"]:
        processed["dlDateOfIssue"] = preferences["dlDateOfIssue"]

    # Languages - array
    if "languages" in preferences and isinstance(preferences["languages"], list):
        processed["languages"] = preferences["languages"]

    # Vehicle types - array
    if "vehicleTypesList" in preferences and isinstance(preferences["vehicleTypesList"], list):
        # Normalize vehicle type names - include all vehicle types and models
        normalized_vehicles = []
        for vehicle in preferences["vehicleTypesList"]:
            vehicle_lower = str(vehicle).lower().strip()

            # Handle specific vehicle models and types
            # Map common variations to standard names
            vehicle_mapping = {
                "tempo traveller": "tempotraveller",
                "tempo": "tempotraveller",
                "innova crysta": "innova crysta",
                "crysta": "innova crysta",
                # Keep all other vehicles as-is (lowercased)
            }

            # Check if vehicle needs mapping
            if vehicle_lower in vehicle_mapping:
                normalized_vehicles.append(vehicle_mapping[vehicle_lower])
            else:
                # Add the vehicle as-is (common types and specific models)
                # This includes: sedan, suv, hatchback, innova, ertiga, dzire, etc.
                normalized_vehicles.append(vehicle_lower)

        # Remove duplicates while preserving order
        seen = set()
        unique_vehicles = []
        for vehicle in normalized_vehicles:
            if vehicle not in seen:
                seen.add(vehicle)
                unique_vehicles.append(vehicle)

        if unique_vehicles:
            processed["vehicleTypesList"] = unique_vehicles

    # Boolean preferences - direct boolean values
    boolean_fields = [
        "isPetAllowed",
        "allowHandicappedPersons",
        "married",
        "availableForCustomersPersonalCar",
        "availableForDrivingInEventWedding",
        "availableForPartTimeFullTime"
    ]

    for field in boolean_fields:
        if field in preferences and isinstance(preferences[field], bool):
            processed[field] = preferences[field]

    # Connections preference - string
    if "connections" in preferences and preferences["connections"] in ["asc", "desc"]:
        processed["connections"] = preferences["connections"]

    # Age preference - number (maximum age)
    if "age" in preferences:
        try:
            age_value = int(preferences["age"])
            if age_value > 0:
                processed["age"] = age_value
        except (ValueError, TypeError):
            pass

    return processed
