from fastapi import APIRouter, Depends

from schemas.ai import SuggestReplyRequest, SuggestReplyResponse
from services.ai_service import suggest_reply
from services.mailbox import Mailbox, call_tool, current_mailbox
from services.usage import ai_budget

router = APIRouter()


@router.post(
    "/suggest-reply",
    response_model=SuggestReplyResponse,
    dependencies=[Depends(ai_budget)],
)
async def suggest_reply_endpoint(
    req: SuggestReplyRequest,
    mailbox: Mailbox = Depends(current_mailbox),
) -> SuggestReplyResponse:
    email_text = await call_tool(mailbox, "gmail_read_message", {"messageId": req.emailId})
    draft = await suggest_reply(email_text, req.instruction)
    return SuggestReplyResponse(draft=draft)
