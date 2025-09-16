# services/api_client.py
"""Simplified API client - only trip creation with preferences"""

import requests
from typing import Dict, Any, Optional
import logging
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_trip_with_preferences(
    customer_details: Dict[str, str],
    pickup_city: str,
    drop_city: str,
    trip_type: str,
    start_date: str,
    end_date: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create a trip with user preferences.
    The Firebase trigger will handle driver notifications automatically.

    Args:
        customer_details: Customer information
        pickup_city: Pickup city
        drop_city: Drop city
        trip_type: Type of trip (one-way/round-trip)
        start_date: Start date in ISO format
        end_date: End date in ISO format (optional)
        preferences: User preferences for the trip

    Returns:
        Trip creation response or None if failed
    """
    logger.info("\n🚗 CREATE_TRIP API CALL")
    logger.info(f"  Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info(f"  Route: {pickup_city} to {drop_city}")
    logger.info(f"  Preferences: {preferences}")

    max_retries = 2  # Reduced retries for faster response

    for attempt in range(max_retries):
        try:
            payload = {
                "customerId": customer_details.get("id"),
                "customerName": customer_details.get("name"),
                "customerPhone": customer_details.get("phone"),
                "customerProfileImage": customer_details.get("profile_image", ""),
                "pickUpLocation": {
                    "city": pickup_city,
                    "coordinates": "",
                    "placeName": ""
                },
                "dropLocation": {
                    "city": drop_city,
                    "coordinates": "",
                    "placeName": ""
                },
                "startDate": start_date,
                "tripType": trip_type,
                "preferences": preferences or {}
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
