from __future__ import annotations

import asyncio
import datetime
import random
import re
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

from Logging_Middleware.logger import Logger

try:
    import uvloop
except ImportError:
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

app = FastAPI()

# Log app startup
Logger.info(stack="main.py", package="service", message="App startup.")

HOSTNAME = "localhost"
PORT = 8000

SHORTCODE_REGEX = re.compile(r"^[a-zA-Z0-9]{4,16}$")

class Item(BaseModel):
    url: str
    validity: Optional[int] = Field(default=30, ge=1)
    shortcode: Optional[str] = None

class ItemResponse(BaseModel):
    shortLink: str
    expiry: datetime.datetime

class ClickDetail(BaseModel):
    timestamp: datetime.datetime
    referrer: Optional[str] = None
    location: Optional[str] = None

class DatabaseHandler:
    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}

    def _generate_shortcode(self) -> str:
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))

    def _is_valid_shortcode(self, code: str) -> bool:
        return bool(SHORTCODE_REGEX.match(code))

    def save(self, item: Item) -> str:
        # Validate custom shortcode if provided
        if item.shortcode:
            if not self._is_valid_shortcode(item.shortcode):
                Logger.warning(stack="main.py", package="db", message=f"Invalid shortcode format: {item.shortcode}")
                raise ValueError("Shortcode must be alphanumeric and 4-16 characters long.")
            if item.shortcode in self.data:
                Logger.warning(stack="main.py", package="db", message=f"Shortcode {item.shortcode} already exists.")
                raise ValueError("Shortcode already exists")
            shortcode = item.shortcode
        else:
            # Generate a unique shortcode
            attempts = 0
            while True:
                shortcode = self._generate_shortcode()
                if shortcode not in self.data:
                    break
                attempts += 1
                if attempts > 10_000:
                    Logger.fatal(stack="main.py", package="db", message="Failed to generate unique shortcode after 10,000 attempts.")
                    raise Exception("Failed to generate unique shortcode.")
        now = datetime.datetime.now(datetime.timezone.utc)
        expiry = now + datetime.timedelta(minutes=item.validity or 30)
        self.data[shortcode] = {
            "url": item.url,
            "validity": item.validity or 30,
            "expiry": expiry,
            "created": now,
            "clicks": 0,
            "click_details": [],
        }
        Logger.info(stack="main.py", package="db", message=f"Shortcode {shortcode} saved.")
        return shortcode

    def get(self, shortcode: str):
        item = self.data.get(shortcode)
        if not item:
            Logger.warning(stack="main.py", package="db", message=f"Shortcode {shortcode} not found.")
            return None
        if datetime.datetime.now(datetime.timezone.utc) > item["expiry"]:
            del self.data[shortcode]
            Logger.info(stack="main.py", package="db", message=f"Shortcode {shortcode} expired and deleted.")
            return None
        Logger.debug(stack="main.py", package="db", message=f"Shortcode {shortcode} retrieved.")
        return item

    def get_stats(self, shortcode: str):
        item = self.data.get(shortcode)
        if not item:
            Logger.warning(stack="main.py", package="db", message=f"Stats requested for non-existent shortcode {shortcode}.")
            return None
        stats = {
            "shortLink": f"http://{HOSTNAME}:{PORT}/{shortcode}",
            "originalUrl": item["url"],
            "created": item["created"].isoformat(),
            "expiry": item["expiry"].isoformat(),
            "clicks": item["clicks"],
            "clickDetails": item["click_details"],
        }
        return stats

    def record_click(self, shortcode: str, referrer: Optional[str], location: Optional[str]):
        item = self.data.get(shortcode)
        if item:
            item["clicks"] += 1
            item["click_details"].append({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "referrer": referrer,
                "location": location,
            })
            Logger.info(stack="main.py", package="db", message=f"Click recorded for shortcode {shortcode}.")

_database_handler = DatabaseHandler()

@app.get("/")
async def root():
    Logger.info(stack="main.py", package="route", message="GET / called.")
    return {"status": "online"}

@app.post("/shorturls", response_model=ItemResponse, status_code=201)
async def create_short_url(item: Item, request: Request):
    Logger.info(stack="main.py", package="route", message="POST /shorturls called.")
    try:
        shortcode = _database_handler.save(item)
        expiry = _database_handler.get(shortcode)["expiry"]
        short_url = f"http://{request.client.host}:{PORT}/{shortcode}"
        Logger.info(stack="main.py", package="route", message=f"Short URL created: {short_url}")
        return ItemResponse(shortLink=short_url, expiry=expiry)
    except ValueError as e:
        Logger.error(stack="main.py", package="route", message=f"Error creating short URL: {str(e)}")
        return JSONResponse(status_code=409, content={"error": str(e)})
    except Exception as e:
        Logger.fatal(stack="main.py", package="route", message=f"Unexpected error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "An unexpected error occurred: " + str(e)})

@app.get("/shorturls/{shortcode}")
async def get_short_url_stats(shortcode: str):
    Logger.info(stack="main.py", package="route", message=f"GET /shorturls/{shortcode} (stats) called.")
    stats = _database_handler.get_stats(shortcode)
    if not stats:
        Logger.warning(stack="main.py", package="route", message=f"Stats not found for shortcode {shortcode}.")
        return JSONResponse(status_code=404, content={"error": "Shortcode not found"})
    return stats

@app.get("/{shortcode}")
async def redirect_short_url(shortcode: str, request: Request, response: Response):
    Logger.info(stack="main.py", package="route", message=f"GET /{shortcode} (redirect) called.")
    item = _database_handler.get(shortcode)
    if not item:
        Logger.warning(stack="main.py", package="route", message=f"Shortcode {shortcode} not found for redirection.")
        return JSONResponse(status_code=404, content={"error": "Shortcode not found"})
    if datetime.datetime.now(datetime.timezone.utc) > item["expiry"]:
        Logger.warning(stack="main.py", package="route", message=f"Shortcode {shortcode} has expired.")
        return JSONResponse(status_code=410, content={"error": "Shortcode has expired"})
    # Track click
    referrer = request.headers.get("referer")
    # For demo, location is not implemented (would require IP geolocation API)
    location = None
    _database_handler.record_click(shortcode, referrer, location)
    Logger.info(stack="main.py", package="route", message=f"Redirecting shortcode {shortcode} to {item['url']}")
    return RedirectResponse(url=item["url"])

