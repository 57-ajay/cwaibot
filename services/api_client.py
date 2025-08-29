# services/api_client.py
"""Fixed API client with proper filter parameter handling"""

import requests
from typing import List, Dict, Any, Optional
import logging
import json
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_driver_ids(
    city: str,
    limit: int = config.DRIVERS_PER_FETCH,
    page: int = 1,
    filters: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Get only driver IDs from the API with proper filter handling

    Args:
        city: City to search for drivers
        limit: Number of drivers to fetch
        page: Page number to fetch
        filters: Optional filters to apply (already processed for API)

    Returns:
        List of driver IDs only
    """
    logger.info(f"\n📍 GET_DRIVERS API CALL (IDs only)")
    logger.info(f"  URL: {config.GET_PREMIUM_DRIVERS_URL}")
    logger.info(f"  Params: city={city}, limit={limit}")

    try:
        # Start with base parameters
        params = {
            "city": city,
            "page": page,
            "limit": limit,
        }

        # Add filters if provided
        if filters:
            logger.info("  🎯 Applying Filters to API Request:")

            # CRITICAL: The filters are already processed and should be added directly to params
            # Don't modify boolean values here as they should already be strings
            for key, value in filters.items():
                params[key] = value
                logger.info(f"     {key}: {value}")

        logger.info(f"  📤 Full Request Parameters: {json.dumps(params, indent=2)}")

        response = requests.get(config.GET_PREMIUM_DRIVERS_URL, params=params, timeout=20)
        logger.info(f"  Response Status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"  ❌ API error: {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return []

        result = response.json()

        if not result.get("success"):
            logger.warning(f"  ⚠️ API returned success=false")
            logger.warning(f"  Message: {result.get('message')}")
            return []

        # Extract only driver IDs
        drivers_data = result.get("data", [])
        driver_ids = [driver.get("id") for driver in drivers_data if driver.get("id")]

        logger.info(f"  ✅ Found {len(driver_ids)} driver IDs matching filters")

        # Log some details for debugging
        if drivers_data and len(drivers_data) > 0:
            logger.info(f"  Sample driver details for validation:")
            sample_driver = drivers_data[0]
            if 'verifiedVehicles' in sample_driver:
                logger.info(f"     Vehicle info available: Yes")
            logger.info(f"     Driver ID: {sample_driver.get('id')}")

        return driver_ids

    except requests.exceptions.RequestException as e:
        logger.error(f"  ❌ Request error: {e}")
        return []
    except Exception as e:
        logger.error(f"  ❌ Error: {e}", exc_info=True)
        return []


def create_trip(
    customer_details: Dict[str, str],
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    start_date: str,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Create a trip using the API

    Args:
        customer_details: Customer information
        pickup_city: Pickup city
        drop_city: Drop city
        trip_type: Type of trip (one-way/round-trip)
        start_date: Start date in ISO format
        end_date: End date in ISO format (optional)

    Returns:
        Trip creation response or None if failed
    """
    logger.info(f"\n🚗 CREATE_TRIP API CALL")
    logger.info(f"  Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info(f"  Route: {pickup_city} to {drop_city}")

    try:
        payload = {
            "customerId": customer_details.get("id"),
            "customerName": customer_details.get("name"),
            "customerPhone": customer_details.get("phone"),
            "customerProfileImage": customer_details.get("profile_image", ""),
            "pickUpLocation": {
                "city": pickup_city,
                "coordinates": "",
                "placeName": "",
            },
            "dropLocation": {
                "city": drop_city,
                "coordinates": "",
                "placeName": "",
            },
            "startDate": start_date,
            "tripType": trip_type,
        }
        if end_date:
            payload["endDate"] = end_date

        response = requests.post(config.CREATE_TRIP_URL, json=payload, timeout=20)
        logger.info(f"  Response Status: {response.status_code}")

        if response.status_code not in [200, 201]:
            logger.error(f"  ❌ API error: {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return None

        response_data = response.json()

        # Return minimal response
        trip_response = {
            "message": response_data.get("message"),
            "tripId": response_data.get("tripId")
        }

        logger.info(f"  ✅ Trip created: {trip_response.get('tripId')}")
        return trip_response

    except requests.exceptions.RequestException as e:
        logger.error(f"  ❌ Request error: {e}")
        return None
    except Exception as e:
        logger.error(f"  ❌ Error: {e}", exc_info=True)
        return None


def send_availability_request(
    trip_id: str,
    driver_ids: List[str],
    trip_details: Dict[str, Any],
    customer_details: Dict[str, Any],
    user_filters: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Send availability request to drivers with properly formatted filters

    Args:
        trip_id: Trip ID
        driver_ids: List of driver IDs to notify
        trip_details: Trip information
        customer_details: Customer information
        user_filters: Applied filters (already processed)

    Returns:
        Availability response or None if failed
    """
    logger.info(f"\n📨 SEND_AVAILABILITY API CALL")
    logger.info(f"  Trip ID: {trip_id}")
    logger.info(f"  Number of Drivers: {len(driver_ids)}")
    logger.info(f"  User Filters for Availability: {user_filters}")

    try:
        # The filters are already in the correct format from process_filters_for_api
        # Just pass them through directly

        # Build payload with actual driver IDs
        payload = {
            "driverIds": driver_ids,  # Use actual driver IDs
            "data": {
                "trip_details": trip_details,
                "customerDetails": {
                    "name": customer_details.get("name"),
                    "id": customer_details.get("id"),
                    "phoneNo": customer_details.get("phone"),
                    "profile_image": customer_details.get("profile_image", ""),
                },
                "message": "Please confirm your availability for this trip.",
            },
            "tripId": trip_id,
            "userFilters": user_filters,  # Pass filters as-is
        }

        logger.info(f"  📤 Sending payload with {len(driver_ids)} driver IDs")

        response = requests.post(
            config.SEND_AVAILABILITY_REQUEST_URL,
            json=payload,
            timeout=20
        )

        logger.info(f"  Response Status: {response.status_code}")

        if response.status_code not in [200, 201]:
            logger.error(f"  ❌ API error: {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return None

        response_data = response.json()

        if not response_data.get("success"):
            logger.error(f"  ❌ Availability request failed")
            logger.error(f"  Response: {response_data}")
            return None

        logger.info(f"  ✅ Availability request sent successfully")

        # Log summary of the response
        summary = response_data.get("summary", {})
        if summary:
            logger.info(f"  📊 Summary:")
            logger.info(f"     - Total Drivers: {summary.get('totalDrivers', 0)}")
            logger.info(f"     - Success Count: {summary.get('successCount', 0)}")
            logger.info(f"     - Failure Count: {summary.get('failureCount', 0)}")

        return response_data

    except requests.exceptions.RequestException as e:
        logger.error(f"  ❌ Request error: {e}")
        return None
    except Exception as e:
        logger.error(f"  ❌ Error: {e}", exc_info=True)
        return None
