from fastapi import APIRouter, HTTPException
from src.core.prompt_templete import PromptGenerator
from src.service.chat_services import get_ai_response
from app.schemas.chat_body import InputData, RegenerateInputData
from src.core.data_processor import ProcessData
from session.city_session_store import ChatSessionStore

router = APIRouter()


def _parse_ai_response(response_text: str) -> dict:
    try:
        return ProcessData.EnsureDict(response_text)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _merge_regenerated_field(
    previous_response: dict,
    generated_response: dict,
    update_field_name: str,
) -> dict:
    if update_field_name not in generated_response:
        raise HTTPException(
            status_code=502,
            detail=f"AI response did not include '{update_field_name}'.",
        )

    updated_response = previous_response.copy()
    updated_response[update_field_name] = generated_response[update_field_name]
    return updated_response


@router.post("/get_suggested_city")
async def get_suggested_city(input_data: InputData):
    prompt = PromptGenerator.gen_prompt()
    response_text = get_ai_response(prompt)
    response = _parse_ai_response(response_text)
    session = 
    )
    return {
        "session_id": session.session_id,
        "response": session.response,
    }


@router.post("/regenerate-suggested_city")
async def regenerate_suggested_city(regenarate_data: RegenerateInputData):
    session = ChatSessionStore.get(regenarate_data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        prompt = PromptGenerator.regenerate_prompt(
            previous_response=session.response,
            update_field_name=regenarate_data.update_field_name,
            user_instruction=regenarate_data.user_instruction,
            image_url=session.image_url,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    response_text = ConfigOpenAI().get_response(prompt)
    generated_response = _parse_ai_response(response_text)
    response = _merge_regenerated_field(
        previous_response=session.response,
        generated_response=generated_response,
        update_field_name=regenarate_data.update_field_name,
    )
    updated_session = ChatSessionStore.update_response(
        session_id=regenarate_data.session_id,
        response=response,
        update_field_name=regenarate_data.update_field_name,
        user_instruction=regenarate_data.user_instruction or "",
    )
    if updated_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return {
        "session_id": updated_session.session_id,
        "response": updated_session.response,
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if not ChatSessionStore.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"message": "Session deleted successfully."}
