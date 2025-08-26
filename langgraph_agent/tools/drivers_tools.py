# langgraph_agent/tools/drivers_tools.py
"""Refactored driver tools - only fetch and store driver IDs"""

import logging
from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
from datetime import datetime, timezone
from services import api_client
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def create_trip_and_check_availability(
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    customer_details: Dict[str, str],
    start_date: str,
    return_date: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Creates a trip and immediately checks driver availability based on preferences.
    Only returns driver IDs, not full driver details.

    Args:
        pickup_city: The city from where the trip starts
        drop_city: The city where the trip ends
        trip_type: The type of trip, must be either 'one-way' or 'round-trip'
        customer_details: Dictionary containing customer's id, name, phone, and profile_image
        start_date: The start date for the trip, in YYYY-MM-DD format
        return_date: (Optional) The return date for a round-trip, in YYYY-MM-DD format
        filters: (Optional) Driver preferences/filters

    Returns:
        Dictionary with operation status and driver IDs
    """
    logger.info("="*50)
    logger.info("STARTING TRIP CREATION AND AVAILABILITY CHECK")
    logger.info(f"Route: {pickup_city} to {drop_city}")
    logger.info(f"Trip Type: {trip_type}")
    logger.info(f"Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info("="*50)

    # STEP 1: CREATE THE TRIP
    logger.info("\n📝 STEP 1: Creating Trip...")

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
            logger.error(f"  ❌ Error parsing date {date_str}: {e}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    # Format dates for API
    formatted_start_date = format_date_for_api(start_date)

    if trip_type.lower() == "round-trip":
        if not return_date:
            logger.error("  ❌ Return date missing for round-trip")
            return {
                "status": "error",
                "message": "Return date is required for a round-trip."
            }
        formatted_end_date = format_date_for_api(return_date)
    else:
        formatted_end_date = formatted_start_date

    # Call trip creation API
    trip_data = api_client.create_trip(
        customer_details,
        pickup_city,
        drop_city,
        trip_type.lower(),
        formatted_start_date,
        formatted_end_date
    )

    if not trip_data or "tripId" not in trip_data:
        logger.error("  ❌ TRIP CREATION FAILED")
        return {
            "status": "error",
            "message": "Failed to create the trip. Please try again."
        }

    trip_id = trip_data.get("tripId")
    logger.info(f"  ✅ TRIP CREATED: {trip_id}")

    # STEP 2: GET DRIVER IDS BASED ON FILTERS
    logger.info(f"\n🚗 STEP 2: Fetching Driver IDs from {pickup_city}...")

    processed_filters = process_filter_types(filters) if filters else None

    # Fetch only driver IDs (not full details)
    driver_ids = api_client.get_driver_ids(
        pickup_city,
        config.DRIVERS_PER_FETCH,
        processed_filters
    )

    if not driver_ids:
        logger.warning(f"  ⚠️ NO DRIVERS FOUND for {pickup_city}")
        return {
            "status": "partial_success",
            "message": "Trip created but no drivers available currently.",
            "trip_id": trip_id,
            "driver_ids": []
        }

    logger.info(f"  ✅ Found {len(driver_ids)} drivers")

    # STEP 3: SEND AVAILABILITY REQUEST
    logger.info(f"\n📤 STEP 3: Sending Availability Requests to {len(driver_ids)} drivers...")

    # Prepare trip details for availability check
    trip_details = {
        "from": pickup_city,
        "to": drop_city,
        "trip_time": datetime.now(timezone.utc).strftime("%I:%M %p"),
        "trip_start_date": datetime.strptime(start_date, "%Y-%m-%d").strftime("%m/%d/%y"),
        "trip_end_date": datetime.strptime(return_date if return_date else start_date, "%Y-%m-%d").strftime("%m/%d/%y"),
        "trip_type": trip_type,
    }

    # Convert filters for availability API
    user_filters = {}
    if processed_filters:
        for key, value in processed_filters.items():
            if isinstance(value, bool):
                user_filters[key] = "true" if value else "false"
            else:
                user_filters[key] = value

    # Send availability request
    availability_response = api_client.send_availability_request(
        trip_id,
        driver_ids,
        trip_details,
        customer_details,
        user_filters
    )

    if not availability_response:
        logger.error("  ❌ AVAILABILITY REQUEST FAILED")
        return {
            "status": "partial_success",
            "message": f"Trip created (ID: {trip_id}) but couldn't notify drivers.",
            "trip_id": trip_id,
            "driver_ids": driver_ids
        }

    logger.info("  ✅ AVAILABILITY REQUESTS SENT")
    logger.info("="*50)
    logger.info("COMPLETED: TRIP CREATED AND DRIVERS NOTIFIED")
    logger.info(f"Trip ID: {trip_id}")
    logger.info(f"Drivers Notified: {len(driver_ids)}")
    logger.info("="*50)

    return {
        "status": "success",
        "message": "I have notified drivers matching your preferences. You'll receive their quotations shortly.",
        "trip_id": trip_id,
        "drivers_notified": len(driver_ids),
        "driver_ids": driver_ids,  # Return only IDs
        "filters_applied": bool(filters)
    }


def process_filter_types(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Process filters to ensure correct data types for API"""
    logger.info("  Processing filter types...")
    processed = {}

    integer_filters = {
        'minAge', 'maxAge', 'minExperience', 'minConnections',
        'minDrivingExperience', 'fraudReports'
    }

    boolean_filters = {
        'isPetAllowed', 'married', 'profileVerified', 'verified',
        'allowHandicappedPersons', 'availableForCustomersPersonalCar',
        'availableForDrivingInEventWedding', 'availableForPartTimeFullTime'
    }

    string_filters = {
        'verifiedLanguages', 'vehicleTypes', 'gender'
    }

    for key, value in filters.items():
        if value is None:
            continue

        try:
            if key in integer_filters:
                processed[key] = int(value)
            elif key in boolean_filters:
                if isinstance(value, bool):
                    processed[key] = value
                elif isinstance(value, str):
                    processed[key] = value.lower() in ['true', '1', 'yes', 'on']
                else:
                    processed[key] = bool(value)
            elif key in string_filters:
                processed[key] = str(value)
            else:
                processed[key] = value

        except (ValueError, TypeError) as e:
            logger.error(f"    Error processing filter '{key}' with value '{value}': {e}")
            continue

    return processed
