# services/api_client.py
"""API client with LLM-powered price estimation and improved trip creation reliability"""

import requests
from typing import List, Dict, Any, Optional
import logging
import json
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base pricing per km for different vehicle types
VEHICLE_BASE_RATES = {
    "hatchback": {"min": 12, "max": 16},
    "sedan": {"min": 14, "max": 18},
    "suv": {"min": 16, "max": 22},
    "innova": {"min": 16, "max": 24},
    "innova_crysta": {"min": 18, "max": 26},
    "tempoTraveller12Seater": {"min": 22, "max": 30},
    "tempo_traveller": {"min": 22, "max": 30}
}

def estimate_distance_with_llm(pickup_city: str, drop_city: str) -> float:
    """
    Use LLM to estimate distance between two cities
    Returns distance in kilometers
    """
    from langchain_google_vertexai import ChatVertexAI
    from langchain_core.messages import HumanMessage

    try:
        # Initialize LLM
        llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.5)

        # Create prompt for distance estimation
        prompt = f"""
        Estimate the road distance between {pickup_city} and {drop_city} in India.

        Instructions:
        - Provide ONLY the distance number in kilometers
        - Consider actual road/highway routes, not straight-line distance
        - Be realistic about Indian road conditions and routes
        - If cities are in the same state, consider intrastate routes
        - If cities are in different states, consider interstate highway routes
        - Return only a number (e.g., 285) - no text, no units

        Examples:
        Delhi to Jaipur: 280
        Mumbai to Pune: 150
        Bangalore to Chennai: 350

        Distance from {pickup_city} to {drop_city}:
        """

        response = llm.invoke([HumanMessage(content=prompt)])

        # Extract distance from response
        distance_text = response.content.strip()

        # Parse the distance
        try:
            # Extract number from response
            import re
            numbers = re.findall(r'\d+', distance_text)
            if numbers:
                distance = float(numbers[0])
                logger.info(f"  🤖 LLM estimated distance {pickup_city} to {drop_city}: {distance} km")
                return distance
            else:
                logger.warning(f"  ⚠️ Could not parse distance from LLM response: {distance_text}")
                return 200.0  # Default fallback
        except (ValueError, IndexError):
            logger.warning(f"  ⚠️ Error parsing LLM distance response: {distance_text}")
            return 200.0  # Default fallback

    except Exception as e:
        logger.error(f"  ❌ Error getting distance from LLM: {e}")
        # Fallback: estimate based on city names if possible
        return estimate_distance_fallback(pickup_city, drop_city)

def estimate_distance_fallback(pickup_city: str, drop_city: str) -> float:
    """
    Fallback distance estimation based on common city pairs and heuristics
    """
    pickup_lower = pickup_city.lower()
    drop_lower = drop_city.lower()

    # Same city
    if pickup_lower == drop_lower:
        return 50.0  # Local trip within city

    # Common inter-city distances (just a few major ones as fallback)
    common_distances = {
        ("delhi", "jaipur"): 280,
        ("jaipur", "delhi"): 280,
        ("mumbai", "pune"): 150,
        ("pune", "mumbai"): 150,
        ("bangalore", "chennai"): 350,
        ("chennai", "bangalore"): 350,
        ("delhi", "agra"): 200,
        ("agra", "delhi"): 200,
        ("delhi", "chandigarh"): 250,
        ("chandigarh", "delhi"): 250,
    }

    # Check if we have this city pair
    city_pair = (pickup_lower, drop_lower)
    if city_pair in common_distances:
        return float(common_distances[city_pair])

    # Heuristic: estimate based on string similarity/regions
    # This is a very rough estimate
    if any(state in pickup_lower or state in drop_lower for state in ["rajasthan", "jaipur", "jodhpur", "udaipur"]):
        if any(state in pickup_lower or state in drop_lower for state in ["rajasthan", "jaipur", "jodhpur", "udaipur"]):
            return 200.0  # Within Rajasthan
        else:
            return 400.0  # Inter-state from Rajasthan

    # Default distance for unknown city pairs
    logger.info(f"  🔄 Using default distance for {pickup_city} to {drop_city}")
    return 300.0  # Conservative average for inter-city travel

def calculate_estimated_prices(pickup_city: str, drop_city: str, trip_type: str = "one-way") -> Dict[str, Dict[str, int]]:
    """
    Calculate estimated prices for all vehicle types using LLM-powered distance estimation
    """
    logger.info(f"🧮 Calculating prices for {pickup_city} to {drop_city} ({trip_type})")

    # Get distance estimate from LLM
    distance = estimate_distance_with_llm(pickup_city, drop_city)

    # For round trips, double the distance
    if trip_type.lower() == "round-trip":
        distance *= 2
        logger.info(f"  🔄 Round trip - doubled distance: {distance} km")

    logger.info(f"  📏 Final distance for pricing: {distance} km")

    estimated_prices = {}

    for vehicle_type, rates in VEHICLE_BASE_RATES.items():
        min_price = int(distance * rates["min"])
        max_price = int(distance * rates["max"])

        # Add minimum fare and rounding
        min_price = max(min_price, 1500)
        max_price = max(max_price, 2000)

        # Round to nearest 50
        min_price = ((min_price + 24) // 50) * 50
        max_price = ((max_price + 24) // 50) * 50

        estimated_prices[vehicle_type] = {
            "min": min_price,
            "max": max_price
        }

    logger.info(f"  💰 Estimated prices calculated for {len(estimated_prices)} vehicle types")
    logger.info(f"  📊 Price range: ₹{min(p['min'] for p in estimated_prices.values())} - ₹{max(p['max'] for p in estimated_prices.values())}")

    return estimated_prices


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
    logger.info("\n📍 GET_DRIVERS API CALL (IDs only)")
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
            logger.warning("  ⚠️ API returned success=false")
            logger.warning(f"  Message: {result.get('message')}")
            return []

        # Extract only driver IDs
        drivers_data = result.get("data", [])
        driver_ids = [driver.get("id") for driver in drivers_data if driver.get("id")]

        logger.info(f"  ✅ Found {len(driver_ids)} driver IDs matching filters")

        # Log some details for debugging
        if drivers_data and len(drivers_data) > 0:
            logger.info("  Sample driver details for validation:")
            sample_driver = drivers_data[0]
            if 'verifiedVehicles' in sample_driver:
                logger.info("     Vehicle info available: Yes")
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
    Create a trip using the API with LLM-powered price estimation
    Improved reliability with retry mechanism

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
    logger.info("\n🚗 CREATE_TRIP API CALL")
    logger.info(f"  Customer: {customer_details.get('name')} (ID: {customer_details.get('id')})")
    logger.info(f"  Route: {pickup_city} to {drop_city}")

    estimated_prices = calculate_estimated_prices(pickup_city, drop_city, trip_type)

    logger.info(f"ESTIMATED PRICES: {estimated_prices}")

    # Retry mechanism for improved reliability
    max_retries = 3
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
                    "placeName": "",
                },
                "dropLocation": {
                    "city": drop_city,
                    "coordinates": "",
                    "placeName": "",
                },
                "startDate": start_date,
                "tripType": trip_type,
                "estimatedPrice": estimated_prices
            }

            if end_date:
                payload["endDate"] = end_date

            logger.info(f"  📤 Attempt {attempt + 1}/{max_retries}")
            logger.info(f"  📊 Estimated prices included: {len(estimated_prices)} vehicle types")

            response = requests.post(config.CREATE_TRIP_URL, json=payload, timeout=30)
            logger.info(f"  Response Status: {response.status_code}")

            if response.status_code in [200, 201]:
                response_data = response.json()

                # Return minimal response
                trip_response = {
                    "message": response_data.get("message"),
                    "tripId": response_data.get("tripId")
                }

                logger.info(f"  ✅ Trip created successfully: {trip_response.get('tripId')}")
                return trip_response
            else:
                logger.error(f"  ❌ API error on attempt {attempt + 1}: {response.status_code}")
                logger.error(f"  Response: {response.text}")

                # If this is the last attempt, don't retry
                if attempt == max_retries - 1:
                    break

                # Wait before retry
                import time
                time.sleep(1)

        except requests.exceptions.Timeout:
            logger.error(f"  ⏰ Timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                break
            import time
            time.sleep(2)

        except requests.exceptions.RequestException as e:
            logger.error(f"  ❌ Request error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                break
            import time
            time.sleep(1)

        except Exception as e:
            logger.error(f"  ❌ Unexpected error on attempt {attempt + 1}: {e}", exc_info=True)
            if attempt == max_retries - 1:
                break
            import time
            time.sleep(1)

    logger.error("  ❌ All trip creation attempts failed")
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
    logger.info("\n📨 SEND_AVAILABILITY API CALL")
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
            logger.error("  ❌ Availability request failed")
            logger.error(f"  Response: {response_data}")
            return None

        logger.info("  ✅ Availability request sent successfully")

        # Log summary of the response
        summary = response_data.get("summary", {})
        if summary:
            logger.info("  📊 Summary:")
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
