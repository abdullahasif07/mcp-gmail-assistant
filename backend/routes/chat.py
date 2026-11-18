from fastapi import APIRouter, Depends, HTTPException

from schemas.chat import ChatRequest, ChatResponse, ConfirmResponse, PendingAction
from services.gemini_service import DEFERRED_TOOLS, chat_once, execute_pending
from services.mailbox import Mailbox, current_mailbox
from services.usage import ai_budget

router = APIRouter()


@router.get("/health")
def chat_health():
    return {"chat": "ok"}


@router.post("", response_model=ChatResponse, dependencies=[Depends(ai_budget)])
async def chat(
    req: ChatRequest,
    mailbox: Mailbox = Depends(current_mailbox),
) -> ChatResponse:
    result = await chat_once(req.message, mailbox)
    pending = PendingAction(**result.pending_action) if result.pending_action else None
    return ChatResponse(reply=result.reply, pendingAction=pending)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    req: PendingAction,
    mailbox: Mailbox = Depends(current_mailbox),
) -> ConfirmResponse:
    if req.tool not in DEFERRED_TOOLS:
        raise HTTPException(status_code=400, detail=f"{req.tool!r} cannot be confirmed")
    text = await execute_pending({"tool": req.tool, "args": req.args}, mailbox)
    return ConfirmResponse(reply=text)
