# langgraph_agent/tools/drivers_tools.py
"""Enhanced driver tools with trip cancellation and smart features"""

import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool
from datetime import datetime, timezone
from services import api_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    logger.info("="*50)
    logger.info("CANCELLING TRIP")
    logger.info(f"Trip ID: {trip_id}")
    logger.info(f"Customer ID: {customer_id}")
    logger.info("="*50)

    try:
        # Call the cancellation API
        result = api_client.cancel_trip(trip_id)

        if result and result.get("status") == "success":
            logger.info(f"✅ Trip {trip_id} cancelled successfully")
            return {
                "status": "success",
                "message": f"Your trip has been cancelled successfully. Trip ID: {trip_id}"
            }
        else:
            logger.error(f"❌ Failed to cancel trip {trip_id}")
            return {
                "status": "error",
                "message": "Unable to cancel the trip. Please try again or contact support at +919403892230"
            }

    except Exception as e:
        logger.error(f"❌ Error cancelling trip: {e}")
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
    source: Optional[str] = "app",
    passenger_count: Optional[int] = None
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
        preferences: (Optional) User preferences for the trip (vehicle type, driver preferences, etc.)
        source: (Optional) Source of the booking - 'app', 'website', or 'whatsapp'
        passenger_count: (Optional) Number of passengers for smart vehicle selection

    Returns:
        Dictionary with trip creation status
    """
    logger.info("="*50)
    logger.info("CREATING TRIP WITH PREFERENCES")
    logger.info(f"Route: {pickup_city} to {drop_city}")
    logger.info(f"Trip Type: {trip_type}")
    logger.info(f"Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info(f"Source: {source}")
    logger.info(f"Passenger Count: {passenger_count}")
    logger.info(f"Preferences: {preferences}")
    logger.info("="*50)

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
            formatted = dt_with_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            return formatted
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    formatted_start_date = format_date_for_api(start_date)

    if trip_type.lower() == "round-trip":
        if not return_date:
            logger.error("Return date missing for round-trip")
            return {
                "status": "error",
                "message": "Return date is required for a round-trip."
            }
        formatted_end_date = format_date_for_api(return_date)
    else:
        formatted_end_date = formatted_start_date

    # Process preferences with smart vehicle selection
    processed_preferences = process_preferences_with_smart_selection(
        preferences,
        passenger_count
    )

    # Call trip creation API with preferences and source
    trip_data = api_client.create_trip_with_preferences(
        customer_details,
        pickup_city,
        drop_city,
        trip_type.lower(),
        formatted_start_date,
        formatted_end_date,
        processed_preferences,
        source  # Pass source to the API
    )

    if not trip_data or "tripId" not in trip_data:
        logger.error("TRIP CREATION FAILED")
        return {
            "status": "error",
            "message": "Failed to create the trip. Please try again."
        }

    trip_id = trip_data.get("tripId")
    logger.info(f"✅ TRIP CREATED SUCCESSFULLY: {trip_id}")
    logger.info("="*50)

    # Return success message
    return {
        "status": "success",
        "message": "Great! I've created your trip and you'll start receiving driver quotations shortly. Drivers will contact you directly with their prices.",
        "trip_id": trip_id
    }


def process_preferences_with_smart_selection(
    preferences: Optional[Dict[str, Any]],
    passenger_count: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process user preferences with smart vehicle selection.
    The LLM handles extraction - we just apply business logic.
    Silently ignores unsupported preferences.
    """
    logger.info("Processing preferences...")

    # List of supported preference fields
    SUPPORTED_PREFERENCES = {
        'vehicles', 'vehicleType', 'language', 'isPetAllowed', 'gender',
        'married', 'minDrivingExperience', 'minAge', 'maxAge', 'minConnections',
        'allowHandicappedPersons', 'availableForCustomersPersonalCar',
        'availableForDrivingInEventWedding', 'availableForPartTimeFullTime',
        'verified', 'profileVerified'
    }

    processed = {}

    # Smart vehicle selection - LLM should have already done this, but double-check
    if passenger_count:
        if passenger_count >= 8:
            logger.info(f"Ensuring Tempo Traveller for {passenger_count} passengers")
            processed['vehicles'] = 'TempoTraveller'
        elif passenger_count >= 5:
            logger.info(f"Ensuring SUV for {passenger_count} passengers")
            processed['vehicles'] = 'SUV'
        # For less than 5, let user preference or no selection

    if not preferences:
        return processed

    # Process only supported preferences, silently ignore others
    for key, value in preferences.items():
        # Check if this is a supported preference
        if key not in SUPPORTED_PREFERENCES and key not in ['isPetFriendly']:
            logger.debug(f"Ignoring unsupported preference: {key}")
            continue

    # Vehicle type preferences - don't override smart selection
    if not processed.get('vehicles'):
        if 'vehicleType' in preferences or 'vehicles' in preferences:
            vehicle_value = preferences.get('vehicleType') or preferences.get('vehicles')
            if isinstance(vehicle_value, list):
                processed['vehicles'] = ','.join(vehicle_value)
            elif vehicle_value:
                processed['vehicles'] = str(vehicle_value)

    # Language preference - direct string
    if 'language' in preferences and preferences['language']:
        processed['language'] = str(preferences['language'])

    # Boolean preferences - API expects string "true" or "false"
    boolean_params = {
        'isPetAllowed': 'isPetAllowed',
        'isPetFriendly': 'isPetAllowed',  # Handle alternate naming
        'married': 'married',
        'allowHandicappedPersons': 'allowHandicappedPersons',
        'availableForCustomersPersonalCar': 'availableForCustomersPersonalCar',
        'availableForDrivingInEventWedding': 'availableForDrivingInEventWedding',
        'availableForPartTimeFullTime': 'availableForPartTimeFullTime',
        'verified': 'verified',
        'profileVerified': 'profileVerified'
    }

    for pref_key, api_param in boolean_params.items():
        if pref_key in preferences:
            value = preferences[pref_key]
            if isinstance(value, bool):
                processed[api_param] = "true" if value else "false"
            elif isinstance(value, str):
                processed[api_param] = "true" if value.lower() in ['true', '1', 'yes'] else "false"
            elif value:  # Any truthy value
                processed[api_param] = "true"

    # Integer preferences - API expects integers
    integer_params = {
        'minDrivingExperience': 'minDrivingExperience',
        'minAge': 'minAge',
        'maxAge': 'maxAge',
        'minConnections': 'minConnections'
    }

    for pref_key, api_param in integer_params.items():
        if pref_key in preferences and preferences[pref_key] is not None:
            try:
                processed[api_param] = int(preferences[pref_key])
            except (ValueError, TypeError):
                logger.warning(f"Could not convert {pref_key} to integer: {preferences[pref_key]}")

    # Gender preference - lowercase string
    if 'gender' in preferences and preferences['gender']:
        gender_value = str(preferences['gender']).lower()
        if gender_value in ['male', 'female']:
            processed['gender'] = gender_value

    logger.info(f"Processed preferences for API: {processed}")
    return processed
