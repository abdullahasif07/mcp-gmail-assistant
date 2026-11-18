from fastapi import APIRouter, Depends, HTTPException

from auth_session import current_refresh_token
from schemas.chat import ChatRequest, ChatResponse, ConfirmResponse, PendingAction
from services.gemini_service import DEFERRED_TOOLS, chat_once, execute_pending

router = APIRouter()


@router.get("/health")
def chat_health():
    return {"chat": "ok"}


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    refresh_token: str = Depends(current_refresh_token),
) -> ChatResponse:
    result = await chat_once(req.message, refresh_token)
    pending = PendingAction(**result.pending_action) if result.pending_action else None
    return ChatResponse(reply=result.reply, pendingAction=pending)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    req: PendingAction,
    refresh_token: str = Depends(current_refresh_token),
) -> ConfirmResponse:
    if req.tool not in DEFERRED_TOOLS:
        raise HTTPException(status_code=400, detail=f"{req.tool!r} cannot be confirmed")
    text = await execute_pending({"tool": req.tool, "args": req.args}, refresh_token)
    return ConfirmResponse(reply=text)
