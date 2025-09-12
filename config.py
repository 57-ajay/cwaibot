# config.py
"""Simplified configuration file"""

import os

# API Configuration
BASE_URL = "https://us-central1-cabswale-ai.cloudfunctions.net"
GET_PREMIUM_DRIVERS_URL = f"{BASE_URL}/cabbot-botApiGetPremiumDriversDev"
CREATE_TRIP_URL = "https://cabbot-botcreatetrip-x7ozexvczq-uc.a.run.app"
SEND_AVAILABILITY_REQUEST_URL = f"{BASE_URL}/cabbot-botSendAvilabilityRequestToDriversDev"

# Environment
PORT = int(os.environ.get("PORT", 8000))

# Driver fetching configuration
DRIVERS_PER_FETCH = 25  # Fetch 25 drivers at a time
