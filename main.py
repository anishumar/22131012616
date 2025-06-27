from __future__ import annotations

from Backend import app
import uvicorn
from Logging_Middleware.logger import Logger
import os

PORT = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    Logger.info(stack="main.py", package="service", message="Starting Uvicorn server.")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
