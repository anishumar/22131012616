from __future__ import annotations

import os
from dotenv import load_dotenv
import requests
from datetime import datetime

load_dotenv()

class Config:
    EMAIL: str = os.getenv("EMAIL")
    NAME: str = os.getenv("NAME")
    ROLLNO: str = os.getenv("ROLLNO")
    ACCESSCODE: str = os.getenv("ACCESSCODE")
    CLIENTID: str = os.getenv("CLIENTID")
    CLIENTSECRET: str = os.getenv("CLIENTSECRET")

    @classmethod
    def get_config(cls) -> dict:
        return {
            "email": cls.EMAIL,
            "name": cls.NAME,
            "rollNo": cls.ROLLNO,
            "accessCode": cls.ACCESSCODE,
            "clientID": cls.CLIENTID,
            "clientSecret": cls.CLIENTSECRET,
        }


class TokenManager:
    API = "http://20.244.56.144/evaluation-service/auth"

    expiry: int = 0
    access_token: str = ""

    @staticmethod
    def get_bearer_access_token() -> str:
        print(Config.get_config())
        response = requests.post(
            TokenManager.API,
            json=Config.get_config(),
        )

        print(response.status_code)

        TokenManager.access_token = response.json().get("access_token", "")
        TokenManager.expiry = response.json().get("expiry", 0)

        print("Access Token Details:")
        print(f"Access Token: {TokenManager.access_token}")
        print(f"Expiry: {TokenManager.expiry}")

        return TokenManager.access_token

    @staticmethod
    def get_access_token() -> str:
        if TokenManager.expiry <= 0:
            return TokenManager.get_bearer_access_token()

        if datetime.now().timestamp() > TokenManager.expiry - 900:
            return TokenManager.get_bearer_access_token()

        if not TokenManager.access_token:
            return TokenManager.get_bearer_access_token()

        return TokenManager.access_token

    @staticmethod
    def get_headers() -> dict:
        return {
            "Authorization": f"Bearer {TokenManager.get_access_token()}",
            "Content-Type": "application/json",
        }
    

class Logger:
    API = "http://20.244.56.144/evaluation-service/logs"
    @staticmethod
    def log(stack: str, level: str, package: str, message: str) -> None:
        headers = TokenManager.get_headers()
        print(headers)
        payload = {
            "stack": "backend",
            "level": level,
            "package": package,
            "message": message,
        }
        response = requests.post(Logger.API, json=payload, headers=headers)
        print(response.status_code, response.json())
        response.raise_for_status()

    @staticmethod
    def debug(stack: str, package: str, message: str) -> None:
        Logger.log(stack, "debug", package, message)

    @staticmethod
    def info(stack: str, package: str, message: str) -> None:
        Logger.log(stack, "info", package, message)

    @staticmethod
    def error(stack: str, package: str, message: str) -> None:
        Logger.log(stack, "error", package, message)
    
    @staticmethod
    def warning(stack: str, package: str, message: str) -> None:
        Logger.log(stack, "warn", package, message)

    @staticmethod
    def fatal(stack: str, package: str, message: str) -> None:
        Logger.log(stack, "fatal", package, message)