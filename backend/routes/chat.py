from fastapi import APIRouter, Depends, HTTPException

from auth_session import Session, current_session
from schemas.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConfirmResponse,
    PendingAction,
)
from services.ai_service import DEFERRED_TOOLS, chat_once, execute_pending
from services.chat_memory import Conversation, chat_memory
from services.mailbox import Mailbox, current_mailbox
from services.usage import ai_budget

router = APIRouter()


def conversation_key(session: Session) -> str:
    return f"{session.mode}:{session.id}"


def current_conversation(session: Session = Depends(current_session)) -> Conversation:
    return chat_memory.get(conversation_key(session))


@router.get("/health")
def chat_health():
    return {"chat": "ok"}


@router.post("", response_model=ChatResponse, dependencies=[Depends(ai_budget)])
async def chat(
    req: ChatRequest,
    mailbox: Mailbox = Depends(current_mailbox),
    conversation: Conversation = Depends(current_conversation),
) -> ChatResponse:
    result = await chat_once(req.message, mailbox, conversation)
    pending = PendingAction(**result.pending_action) if result.pending_action else None
    return ChatResponse(reply=result.reply, pendingAction=pending, sent=result.sent)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    req: PendingAction,
    mailbox: Mailbox = Depends(current_mailbox),
    conversation: Conversation = Depends(current_conversation),
) -> ConfirmResponse:
    if req.tool not in DEFERRED_TOOLS:
        raise HTTPException(status_code=400, detail=f"{req.tool!r} cannot be confirmed")
    text = await execute_pending({"tool": req.tool, "args": req.args}, mailbox)
    # Let the model know the draft went out, so follow-ups make sense.
    conversation.pending = None
    conversation.record_assistant(text)
    return ConfirmResponse(reply=text)


@router.post("/discard")
def discard(conversation: Conversation = Depends(current_conversation)):
    """User dismissed the draft card: forget it, so a later "yes" in chat
    can't send it."""
    if conversation.pending is not None:
        conversation.pending = None
        conversation.record_assistant("Draft discarded.")
    return {"ok": True}


@router.get("/history", response_model=ChatHistoryResponse)
def history(conversation: Conversation = Depends(current_conversation)) -> ChatHistoryResponse:
    pending = conversation.pending
    return ChatHistoryResponse(
        messages=[ChatMessage(**m) for m in conversation.transcript],
        pendingAction=PendingAction(**pending) if pending else None,
    )


@router.delete("/history")
def clear_history(session: Session = Depends(current_session)):
    chat_memory.clear(conversation_key(session))
    return {"ok": True}
