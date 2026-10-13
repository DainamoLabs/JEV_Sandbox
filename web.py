"""Local Jevos demo. Start with: python web.py"""

import argparse
import time
from pathlib import Path
from typing import Any, Literal

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import response as jev

ROOT = Path(__file__).parent
app = FastAPI(title="Jevos playground", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

EXAMPLES = [
    {"id": "plain", "label": "Plain text", "request": jev.PLAIN},
    {"id": "multi", "label": "Multiple questions", "request": jev.MULTI_QUESTION},
    {"id": "conversation", "label": "Conversation", "request": jev.CONVERSATION_HISTORY},
    {"id": "happy", "label": "Happy customer", "request": jev.HAPPY_CUSTOMER},
    {"id": "returns", "label": "Return policy", "request": jev.RETURN_POLICY},
    {"id": "email", "label": "Email triage", "request": jev.EMAIL_TRIAGE},
    {"id": "bug", "label": "Bug report", "request": jev.BUG_REPORT},
]


class Question(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: str = Field(min_length=1, max_length=4000)

    @field_validator("instructions")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Enter a question.")
        return value.strip()


class DecisionRequest(BaseModel):
    state: str | dict[str, Any] | list[Any]
    questions: dict[str, Question] = Field(min_length=1, max_length=12)

    @field_validator("state")
    @classmethod
    def nonempty(cls, value):
        if not value or (isinstance(value, str) and not value.strip()):
            raise ValueError("Enter some context first.")
        return value


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/examples")
def examples():
    return EXAMPLES


@app.get("/api/health")
def health():
    try:
        result = requests.get(f"{jev.LLAMA_URL}/health", timeout=3)
        result.raise_for_status()
    except requests.RequestException:
        return {"ready": False}
    return {"ready": True}


@app.post("/api/decide")
def decide(payload: DecisionRequest):
    start = time.perf_counter()
    try:
        result = jev.ask_jev(payload.model_dump())
    except requests.Timeout as exc:
        raise HTTPException(504, "The model took too long to respond. Try again.") from exc
    except requests.ConnectionError as exc:
        raise HTTPException(
            503, f"Cannot reach llama.cpp at {jev.LLAMA_URL}. Start the server and try again."
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, "llama.cpp could not complete this request. Check its server logs.") from exc
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, f"Could not read the model's answer: {exc}") from exc
    return {**result, "elapsed_ms": round((time.perf_counter() - start) * 1000)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--llama-url", default=jev.LLAMA_URL)
    args = parser.parse_args()
    jev.LLAMA_URL = args.llama_url.rstrip("/")
    uvicorn.run(app, host="127.0.0.1", port=args.port)
