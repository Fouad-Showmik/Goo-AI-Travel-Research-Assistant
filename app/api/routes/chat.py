import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import StreamingResponse

from app.clients.llm_client import LLMClient, LLMClientError
from app.core.limiter import limiter
from app.schemas.chat import SESSION_ID_PATTERN, ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.session_store import session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def get_chat_service():
    return ChatService(LLMClient(), session_store)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
SessionIdDep = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


@router.post("", response_model=ChatResponse)
@limiter.limit("10/minute")
@limiter.limit("100/day")
def chat(request: Request, body: ChatRequest, service: ChatServiceDep):
    try:
        return service.ask(body.session_id, body.message)
    except LLMClientError:
        raise HTTPException(status_code=502, detail="Sorry, I'm having trouble right now. Please try again.")

#Stream assistant events to the browser using Server-Sent Events.
@router.post("/stream")
@limiter.limit("10/minute")
@limiter.limit("100/day")

def stream_chat(request: Request, body: ChatRequest, service: ChatServiceDep):
    #  # Flush the HTTP response immediately so the browser knows the stream opened.
    def event_stream():
        yield ": connected\n\n"

        try:
            for event in service.stream(body.session_id, body.message):
                event_name = event.get("type", "message")
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {payload}\n\n"

        except LLMClientError:
            payload = json.dumps({
                    "type": "error",
                    "message": "Sorry, I'm having trouble right now. Please try again.",
            })
            yield f"event: error\ndata: {payload}\n\n"
        except Exception:
            # Do not expose internal exception details to the browser.
            logger.exception("Unexpected error during chat streaming")
            payload = json.dumps({
                "type": "error",
                "message": "Something went wrong while preparing your trip. Please try again.",
            })
            yield f"event: error\ndata: {payload}\n\n"
             
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

@router.delete("/{session_id}", status_code=204)
def reset_chat(service: ChatServiceDep, session_id: SessionIdDep):
    service.reset(session_id)