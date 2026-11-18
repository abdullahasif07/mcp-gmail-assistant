from fastapi import APIRouter, Depends

from auth_session import current_refresh_token
from schemas.ai import SuggestReplyRequest, SuggestReplyResponse
from services.gemini_service import suggest_reply
from services.mcp_service import call_mcp_tool

router = APIRouter()


@router.post("/suggest-reply", response_model=SuggestReplyResponse)
async def suggest_reply_endpoint(
    req: SuggestReplyRequest,
    refresh_token: str = Depends(current_refresh_token),
) -> SuggestReplyResponse:
    email_text = await call_mcp_tool(
        "gmail_read_message", {"messageId": req.emailId}, refresh_token
    )
    draft = await suggest_reply(email_text, req.instruction)
    return SuggestReplyResponse(draft=draft)
