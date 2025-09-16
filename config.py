# config.py
"""Simplified configuration - only trip creation endpoint"""

import os

# API Configuration - Only trip creation endpoint needed
BASE_URL = "https://us-central1-cabswale-ai.cloudfunctions.net"
CREATE_TRIP_URL = "https://cabbot-botcreatetrip-x7ozexvczq-uc.a.run.app"

# Environment
PORT = int(os.environ.get("PORT", 8000))
