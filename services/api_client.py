# services/api_client.py
"""Enhanced API client with trip cancellation and source tracking"""

from fastapi.params import Query
import requests
from typing import Dict, Any, Optional
import logging
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cancel_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    """
    Cancel an existing trip.

    Args:
        trip_id: The ID of the trip to cancel

    Returns:
        Cancellation response or None if failed
    """
    logger.info(f"\n🚫 CANCEL_TRIP API CALL")
    logger.info(f"  Trip ID: {trip_id}")

    try:
        cancel_url = "https://us-central1-cabswale-ai.cloudfunctions.net/cabbot-botCancelTrip"

        payload = {
            "tripId": trip_id
        }

        response = requests.get(
            cancel_url,
            params=payload,
            timeout=10
        )

        logger.info(f"  Response Status: {response.status_code}")

        if response.status_code in [200, 201]:
            response_data = response.json()
            logger.info(f"  ✅ Trip cancelled successfully")
            return {
                "status": "success",
                "message": response_data.get("message", "Trip cancelled successfully")
            }
        else:
            logger.error(f"  ❌ API error: {response.status_code}")
            return {
                "status": "error",
                "message": "Failed to cancel trip"
            }

    except requests.exceptions.Timeout:
        logger.error(f"  ⏰ Timeout during trip cancellation")
        return {
            "status": "error",
            "message": "Request timed out"
        }
    except Exception as e:
        logger.error(f"  ❌ Unexpected error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def create_trip_with_preferences(
    customer_details: Dict[str, str],
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    start_date: str,
    end_date: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    source: str = "None",
    pickup_location_object: Optional[Dict[str, Any]] = None,
    drop_location_object: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create a trip with user preferences and source tracking.
    The Firebase trigger will handle driver notifications automatically.

    Args:
        customer_details: Customer information
        pickup_city: Pickup city
        drop_city: Drop city
        trip_type: Type of trip (one-way/round-trip)
        start_date: Start date in ISO format
        end_date: End date in ISO format (optional)
        preferences: User preferences for the trip
        source: Source of booking ('app', 'website', 'whatsapp', or  'None')

    Returns:
        Trip creation response or None if failed
    """
    logger.info("\n🚗 CREATE_TRIP API CALL")
    logger.info(f"  Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info(f"  Route: {pickup_city} to {drop_city}")
    logger.info(f"  Source: {source}")
    logger.info(f"  Preferences: {preferences}")
    logger.info(f"  Has Pickup Object: {pickup_location_object is not None}")
    logger.info(f"  Has Drop Object: {drop_location_object is not None}")


    max_retries = 2

    for attempt in range(max_retries):
        try:
            if pickup_location_object:
                    pickup_location = pickup_location_object
            else:
                pickup_location = {
                    "city": pickup_city,
                    "coordinates": "",
                    "placeName": "",
                    "state": "",
                    "address": ""
                }

            if drop_location_object:
                drop_location = drop_location_object
            else:
                drop_location = {
                    "city": drop_city,
                    "coordinates": "",
                    "placeName": "",
                    "state": "",
                    "address": ""
                }
            payload = {
                "customerId": customer_details.get("id"),
                "customerName": customer_details.get("name"),
                "customerPhone": customer_details.get("phone"),
                "customerProfileImage": customer_details.get("profile_image", ""),
                "pickUpLocation": pickup_location,
                "dropLocation": drop_location,
                "startDate": start_date,
                "tripType": trip_type,
                "preferences": preferences or {},
                "source": source
            }

            if end_date:
                payload["endDate"] = end_date

            response = requests.post(
                config.CREATE_TRIP_URL,
                json=payload,
                timeout=15
            )

            logger.info(f"  Response Status: {response.status_code}")

            if response.status_code in [200, 201]:
                response_data = response.json()

                trip_response = {
                    "message": response_data.get("message"),
                    "tripId": response_data.get("tripId")
                }

                logger.info(f"  ✅ Trip created successfully: {trip_response.get('tripId')}")
                return trip_response
            else:
                logger.error(f"  ❌ API error on attempt {attempt + 1}: {response.status_code}")
                if attempt == max_retries - 1:
                    break

        except requests.exceptions.Timeout:
            logger.error(f"  ⏰ Timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                break

        except Exception as e:
            logger.error(f"  ❌ Unexpected error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                break

    logger.error("  ❌ Trip creation failed")
    return None
