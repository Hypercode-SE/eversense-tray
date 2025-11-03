import datetime
import logging
import time
from zoneinfo import ZoneInfo

import requests

STOCKHOLM = ZoneInfo("Europe/Stockholm")


class EversenseClient:
    LOGIN_URL = "https://ousiamapialpha.eversensedms.com/connect/token"
    USER_DETAILS_URL = "https://ousalphaapiservices.eversensedms.com/api/Users/GetUserDetails?TimeZoneOffset=-120"
    GLUCOSE_URL = "https://ousalphaapiservices.eversensedms.com//TransmitterLog/GetSensorGlucoseEvents"

    def __init__(self, username, password, otp_factor="email", otp_mode="request"):
        self.username = username
        self.password = password
        self.otp_factor = otp_factor
        self.otp_mode = otp_mode
        self.access_token = None
        self.token_expiry = 0
        self.user_id = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("[Init] EverSense client initialized")

    def login(self):
        data = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
            "client_id": "dms",
            "client_secret": "secret",
            "otp_factor": self.otp_factor,
            "otp_mode": self.otp_mode,
        }
        try:
            resp = requests.post(self.LOGIN_URL, data=data)
            resp.raise_for_status()
            token_data = resp.json()
            self.access_token = token_data["access_token"]
            self.token_expiry = time.time() + token_data.get("expires_in", 43200) - 60
            self.logger.debug(f"[Login] Success, token expires in {token_data.get('expires_in', 43200)}s")
            return True
        except Exception as e:
            self.logger.error(f"[Login] Failed: {e}")
            return False

    def ensure_token_valid(self):
        if not self.access_token or time.time() > self.token_expiry:
            self.logger.debug("[Token] Expired or missing, re-login needed")
            if not self.login():
                raise RuntimeError("Login failed, cannot refresh token")

    def fetch_user_id(self):
        self.ensure_token_valid()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            resp = requests.get(self.USER_DETAILS_URL, headers=headers)
            resp.raise_for_status()
            user_data = resp.json()
            self.user_id = user_data.get("UserID")
            self.logger.debug(f"[User] UserID fetched: {self.user_id}")
            return self.user_id
        except Exception as e:
            self.logger.error(f"[User] Failed to fetch UserID: {e}")
            return None

    def fetch_glucose_data(self, from_dt: datetime.datetime, to_dt: datetime.datetime):
        self.ensure_token_valid()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        to_dt_end = to_dt.astimezone(STOCKHOLM).replace(hour=23, minute=59, second=59, microsecond=999999)
        tz_offset_minutes = -int(to_dt_end.utcoffset().total_seconds() // 60)
        json_data = {
            "FromDateStr": from_dt.strftime("%Y-%m-%dT%H:%M:%S+02:00"),
            "ToDateStr": to_dt_end.strftime("%Y-%m-%dT%H:%M:%S+02:00"),
            "TimeZoneOffset": tz_offset_minutes,
            "UserID": self.user_id,
            "startDate": from_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "endDate": to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        self.logger.debug(f"[Glucose] Fetching glucose data from {from_dt} to {to_dt}")
        try:
            resp = requests.post(self.GLUCOSE_URL, headers=headers, json=json_data)
            resp.raise_for_status()
            data = resp.json()
            # Convert all timestamps to UTC
            for event in data:
                if "EventDate" in event:
                    local_time = datetime.datetime.fromisoformat(event["EventDate"])
                    utc_time = local_time.astimezone(datetime.timezone.utc)
                    event["EventDate"] = utc_time.isoformat()
            return data
        except Exception as e:
            self.logger.error(f"[Glucose] Fetch failed: {e}")
            return None
