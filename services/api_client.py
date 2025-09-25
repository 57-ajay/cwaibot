# services/api_client.py
"""Clean and optimized API client with proper preference handling"""

import requests
from typing import Dict, Any, Optional
import logging
import config

# Minimal logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


def cancel_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    """
    Cancel an existing trip.

    Args:
        trip_id: The ID of the trip to cancel

    Returns:
        Cancellation response or None if failed
    """
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

        if response.status_code in [200, 201]:
            response_data = response.json()
            return {
                "status": "success",
                "message": response_data.get("message", "Trip cancelled successfully")
            }
        else:
            logger.error(f"Cancel trip API error: {response.status_code}")
            return {
                "status": "error",
                "message": "Failed to cancel trip"
            }

    except requests.exceptions.Timeout:
        logger.error("Cancel trip request timed out")
        return {
            "status": "error",
            "message": "Request timed out"
        }
    except Exception as e:
        logger.error(f"Unexpected error cancelling trip: {e}")
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
    Create a trip with user preferences.

    The preferences should be in exact format:
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
        "age": 40
    }

    Returns:
        Trip creation response or None if failed
    """
    max_retries = 2

    for attempt in range(max_retries):
        try:
            # Prepare location objects
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

            # Build payload with exact preference format
            payload = {
                "customerId": customer_details.get("id"),
                "customerName": customer_details.get("name"),
                "customerPhone": customer_details.get("phone"),
                "customerProfileImage": customer_details.get("profile_image", ""),
                "pickUpLocation": pickup_location,
                "dropLocation": drop_location,
                "startDate": start_date,
                "tripType": trip_type,
                "preferences": preferences or {},  # Pass exact preferences as provided
                "source": source
            }

            if end_date:
                payload["endDate"] = end_date

            response = requests.post(
                config.CREATE_TRIP_URL,
                json=payload,
                timeout=15
            )

            if response.status_code in [200, 201]:
                response_data = response.json()

                trip_response = {
                    "message": response_data.get("message"),
                    "tripId": response_data.get("tripId")
                }

                logger.info(f"Trip created: {trip_response.get('tripId')}")
                return trip_response
            else:
                logger.error(f"API error (attempt {attempt + 1}): {response.status_code}")
                if attempt == max_retries - 1:
                    break

        except requests.exceptions.Timeout:
            logger.error(f"Timeout (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                break

        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                break

    logger.error("Trip creation failed after all attempts")
    return None
