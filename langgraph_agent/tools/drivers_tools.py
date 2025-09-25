# langgraph_agent/tools/drivers_tools.py
"""Clean and optimized driver tools with trip modification support"""

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
                "message": f"Your trip has been cancelled successfully."
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
def handle_trip_modification(
    existing_trip_id: str,
    customer_details: Dict[str, str],
    existing_pickup: str,
    existing_drop: str,
    existing_trip_type: str,
    existing_start_date: str,
    existing_end_date: Optional[str] = None,
    existing_preferences: Optional[Dict[str, Any]] = None,
    existing_passenger_count: Optional[int] = None,
    new_pickup: Optional[str] = None,
    new_drop: Optional[str] = None,
    new_trip_type: Optional[str] = None,
    new_start_date: Optional[str] = None,
    new_end_date: Optional[str] = None,
    new_preferences: Optional[Dict[str, Any]] = None,
    new_passenger_count: Optional[int] = None,
    source: Optional[str] = "None",
    pickup_location_object: Optional[Dict[str, Any]] = None,
    drop_location_object: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Handles trip modification by cancelling existing trip and creating a new one with updated details.
    This tool should be used when user wants to modify preferences, date, or trip type for an existing trip.

    Args:
        existing_trip_id: The ID of the existing trip to modify
        customer_details: Dictionary containing customer's id, name, phone, and profile_image
        existing_pickup: Current pickup city
        existing_drop: Current drop city
        existing_trip_type: Current trip type
        existing_start_date: Current start date
        existing_end_date: Current end date (for round trips)
        existing_preferences: Current preferences
        existing_passenger_count: Current passenger count
        new_pickup: New pickup city (if changed)
        new_drop: New drop city (if changed)
        new_trip_type: New trip type (if changed)
        new_start_date: New start date (if changed)
        new_end_date: New end date (if changed)
        new_preferences: New/additional preferences (will be merged with existing)
        new_passenger_count: New passenger count (if changed)
        source: Source of the booking
        pickup_location_object: Pickup location details
        drop_location_object: Drop location details

    Returns:
        Dictionary with modification status and new trip ID
    """
    try:
        # Step 1: Cancel existing trip (silently)
        if existing_trip_id:
            cancel_result = api_client.cancel_trip(existing_trip_id)
            if not cancel_result or cancel_result.get("status") != "success":
                logger.warning(f"Could not cancel existing trip {existing_trip_id}, proceeding with new trip creation")

        # Step 2: Prepare merged details for new trip
        # Use new values if provided, otherwise keep existing
        final_pickup = new_pickup if new_pickup else existing_pickup
        final_drop = new_drop if new_drop else existing_drop
        final_trip_type = new_trip_type if new_trip_type else existing_trip_type
        final_start_date = new_start_date if new_start_date else existing_start_date
        final_passenger_count = new_passenger_count if new_passenger_count else existing_passenger_count

        # Handle end date for round trips
        if final_trip_type and final_trip_type.lower() == "round-trip":
            final_end_date = new_end_date if new_end_date else existing_end_date
        else:
            final_end_date = None

        # Merge preferences (new preferences override existing)
        final_preferences = existing_preferences.copy() if existing_preferences else {}
        if new_preferences:
            final_preferences.update(new_preferences)

        # Process preferences with smart vehicle selection
        processed_preferences = process_preferences(final_preferences, final_passenger_count)

        # Step 3: Create new trip with merged details
        trip_data = create_trip_internal(
            customer_details,
            final_pickup,
            final_drop,
            final_trip_type,
            final_start_date,
            final_end_date,
            processed_preferences,
            source,
            pickup_location_object,
            drop_location_object
        )

        if not trip_data or "tripId" not in trip_data:
            return {
                "status": "error",
                "message": "Failed to update the trip. Please try again."
            }

        new_trip_id = trip_data.get("tripId")
        logger.info(f"Trip modified: {existing_trip_id} -> {new_trip_id}")

        # Determine what was changed for the message
        changes = []
        if new_preferences:
            pref_list = []
            if "gender" in new_preferences:
                pref_list.append(f"{new_preferences['gender']} driver")
            if "languages" in new_preferences:
                pref_list.append(f"{', '.join(new_preferences['languages'])} speaking")
            if "vehicleTypesList" in new_preferences:
                pref_list.append(f"{', '.join(new_preferences['vehicleTypesList'])} vehicle")
            if pref_list:
                changes.append(f"preferences ({', '.join(pref_list)})")

        if new_start_date:
            changes.append(f"date to {new_start_date}")
        if new_trip_type:
            changes.append(f"trip type to {new_trip_type}")
        if new_end_date and final_trip_type == "round-trip":
            changes.append(f"return date to {new_end_date}")
        if new_passenger_count:
            changes.append(f"passenger count to {new_passenger_count}")

        change_text = ", ".join(changes) if changes else "your requirements"

        return {
            "status": "success",
            "message": f"I've updated your trip with {change_text}. You'll receive fresh quotations soon!",
            "old_trip_id": existing_trip_id,
            "new_trip_id": new_trip_id
        }

    except Exception as e:
        logger.error(f"Error modifying trip: {e}")
        return {
            "status": "error",
            "message": "Failed to modify the trip. Please try again or contact support at +919403892230"
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
    # Process preferences with smart vehicle selection
    processed_preferences = process_preferences(preferences, passenger_count)

    # Call internal creation function
    trip_data = create_trip_internal(
        customer_details,
        pickup_city,
        drop_city,
        trip_type,
        start_date,
        return_date,
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


def create_trip_internal(
    customer_details: Dict[str, str],
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    start_date: str,
    end_date: Optional[str] = None,
    processed_preferences: Optional[Dict[str, Any]] = None,
    source: str = "None",
    pickup_location_object: Optional[Dict[str, Any]] = None,
    drop_location_object: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Internal function to create a trip (used by both create and modify functions)
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
        if not end_date:
            # For round trips without end date, use start date
            formatted_end_date = formatted_start_date
        else:
            formatted_end_date = format_date_for_api(end_date)
    else:
        formatted_end_date = formatted_start_date

    # Call trip creation API
    return api_client.create_trip_with_preferences(
        customer_details,
        pickup_city,
        drop_city,
        trip_type.lower(),
        formatted_start_date,
        formatted_end_date,
        processed_preferences or {},
        source,
        pickup_location_object,
        drop_location_object
    )


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
                "innova crysta": "innovaCrysta",
                "crysta": "innovaCrysta",
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
