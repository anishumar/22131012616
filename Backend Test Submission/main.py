from __future__ import annotations

import asyncio
import datetime
import random
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

try:
    import uvloop
except ImportError:
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

app = FastAPI()


class Item(BaseModel):
    url: str
    validity: Optional[int] = Field(default=30, ge=1)
    shortcode: Optional[str] = Field(
        default_factory=lambda: "".join(
            random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6)
        )
    )


class ItemResponse(BaseModel):
    shortLink: str
    expiry: datetime.datetime


class DatabaseHandler:
    def __init__(self):
        self.data = {}

    def save(self, item: Item):
        shortcode = item.shortcode
        if shortcode in self.data:
            raise ValueError("Shortcode already exists")

        self.data[shortcode] = {
            "url": item.url,
            "validity": item.validity,
            "expiry": datetime.datetime.now() + datetime.timedelta(minutes=item.validity),
        }
        return shortcode

    def get(self, shortcode: str):
        item = self.data.get(shortcode)
        if not item:
            return None

        if datetime.datetime.now() > item["expiry"]:
            del self.data[shortcode]
            return None

        return item


_database_handler = DatabaseHandler()


@app.get("/")
async def root():
    return {"status": "online"}


@app.post("/shorturls")
async def create_short_url(item: Item):
    try:
        shortcode = _database_handler.save(item)
        expiry = _database_handler.get(shortcode)["expiry"]
        return ItemResponse(shortLink=shortcode, expiry=expiry)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": "An unexpected error occurred: " + str(e)}


@app.get("/shorturls/{shortcode}")
async def redirect_short_url(shortcode: str):
    item = _database_handler.get(shortcode)
    if not item:
        return {"error": "Shortcode not found"}

    if datetime.datetime.now() > item["expiry"]:
        return {"error": "Shortcode has expired"}

    return RedirectResponse(url=item["url"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
