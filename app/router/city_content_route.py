from fastapi import APIRouter, HTTPException
from src.core.prompt_templete import PromptGenerator
from src.service.chat_services import get_ai_response
from app.schemas.city_body import InputData, RegenerateInputData, RegenerateActivityInputData
from src.core.data_processor import ProcessData
from session.city_session_store import CitySessionStore, ActivitySessionStore

router = APIRouter()


def _parse_ai_response(response_text: str) -> dict:
    """Parse AI response text and convert to structured dict."""
    try:
        return ProcessData.EnsureDict(response_text)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _merge_regenerated_field(
    previous_response: dict,
    generated_response: dict,
    update_field_name: str,
) -> dict:
    """Merge regenerated field into previous response."""
    if update_field_name not in generated_response:
        raise HTTPException(
            status_code=502,
            detail=f"AI response did not include '{update_field_name}'.",
        )
    updated_response = previous_response.copy()
    updated_response[update_field_name] = generated_response[update_field_name]
    return updated_response


# ==================== CITY SUGGESTION FLOW ====================

@router.post("/get_suggested_city")
async def get_suggested_city(input_data: InputData):
    """
    GENERATE: First time user answers questions → get city suggestions.
    - Stores Q&A and city suggestion in session.
    - Returns session_id for future regenerate calls.
    """
    try:
        # Generate prompt from user's Q&A
        prompt = PromptGenerator.gen_city_suggestion_prompt(
            questions_answers=input_data.questions_answers,
            preferred_destinations=input_data.preferred_destinations,
            hope_of_this_trip=input_data.hope_of_this_trip,
        )
        
        # Call AI to get city suggestions
        response_text = get_ai_response(prompt)
        response = _parse_ai_response(response_text)
        
        # Create session and store Q&A + suggestions
        session = CitySessionStore.create(
            questions_answers=input_data.questions_answers,
            suggested_cities=response.get("suggested_cities", []),
            response=response,
        )
        
        return {
            "session_id": session.session_id,
            "suggested_cities": session.suggested_cities,
            "response": session.response,
        }
    
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/regenerate_suggested_city")
async def regenerate_suggested_city(regenerate_data: RegenerateInputData):
    """
    REGENERATE: User wants different city suggestions (same Q&A, new suggestions).
    - Retrieves previous Q&A from session.
    - Calls AI again (optionally excluding previous suggestions).
    - Overwrites suggested_cities in session.
    - Keeps Q&A history intact.
    """
    # Fetch existing session
    session = CitySessionStore.get(regenerate_data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    try:
        # Build regenerate prompt using stored Q&A
        prompt = PromptGenerator.regenerate_city_suggestion_prompt(
            questions_answers=session.questions_answers,
            previous_suggestions=session.suggested_cities,
            user_instruction=regenerate_data.user_instruction,
        )
        
        # Call AI for new suggestions
        response_text = get_ai_response(prompt)
        generated_response = _parse_ai_response(response_text)
        
        # Merge new suggestions into response
        response = _merge_regenerated_field(
            previous_response=session.response,
            generated_response=generated_response,
            update_field_name="suggested_cities",
        )
        
        # Update session with new suggestions
        updated_session = CitySessionStore.update_response(
            session_id=regenerate_data.session_id,
            response=response,
            update_field_name="suggested_cities",
            user_instruction=regenerate_data.user_instruction or "",
        )
        
        if updated_session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        
        return {
            "session_id": updated_session.session_id,
            "suggested_cities": updated_session.suggested_cities,
            "response": updated_session.response,
        }
    
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# ==================== ACTIVITY/TOUR PLAN FLOW ====================

@router.post("/get_tour_plan")
async def get_tour_plan(
    session_id: str,
    selected_city: str,  # Which city from suggestions user selected
):
    """
    GENERATE: First time → create day-wise activity plan for selected city.
    - Creates separate activity session (linked to city session).
    - Stores generated activities in session.
    - Returns activity_session_id for future regenerate calls.
    """
    # Fetch parent city session
    city_session = CitySessionStore.get(session_id)
    if city_session is None:
        raise HTTPException(status_code=404, detail="City session not found.")
    
    try:
        # Check if activity session already exists for this city (to avoid re-generation)
        activity_session = ActivitySessionStore.get_by_city(
            session_id=session_id,
            city_name=selected_city,
        )
        
        if activity_session is not None:
            # Activities already generated → return cached version
            return {
                "activity_session_id": activity_session.activity_session_id,
                "city": activity_session.city,
                "tour_plan": activity_session.tour_plan,
                "source": "cached",  # Indicate this came from session, not AI
            }
        
        # No cached activities → call AI to generate
        prompt = PromptGenerator.gen_tour_plan_prompt(
            questions_answers=city_session.questions_answers,
            selected_city=selected_city,
            trip_length_days=city_session.questions_answers.trip_length_days,
        )
        
        response_text = get_ai_response(prompt)
        response = _parse_ai_response(response_text)
        
        # Create new activity session
        activity_session = ActivitySessionStore.create(
            parent_session_id=session_id,
            city_name=selected_city,
            tour_plan=response.get("tour_plan", []),
            response=response,
        )
        
        return {
            "activity_session_id": activity_session.activity_session_id,
            "city": activity_session.city,
            "tour_plan": activity_session.tour_plan,
            "source": "generated",
        }
    
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/regenerate_tour_plan")
async def regenerate_tour_plan(regenerate_data: RegenerateActivityInputData):
    """
    REGENERATE: User wants different day-wise activities (same city, new plan).
    - Optionally regenerate single day or entire itinerary.
    - Retrieves Q&A from parent city session.
    - Calls AI again.
    - Overwrites activities in session.
    """
    # Fetch activity session
    activity_session = ActivitySessionStore.get(regenerate_data.activity_session_id)
    if activity_session is None:
        raise HTTPException(status_code=404, detail="Activity session not found.")
    
    # Fetch parent city session for Q&A
    city_session = CitySessionStore.get(activity_session.parent_session_id)
    if city_session is None:
        raise HTTPException(status_code=404, detail="Parent city session not found.")
    
    try:
        # Build regenerate prompt
        prompt = PromptGenerator.regenerate_tour_plan_prompt(
            questions_answers=city_session.questions_answers,
            city_name=activity_session.city,
            current_tour_plan=activity_session.tour_plan,
            day_to_regenerate=regenerate_data.day_to_regenerate,  # None = all days
            user_instruction=regenerate_data.user_instruction,
        )
        
        # Call AI for new activities
        response_text = get_ai_response(prompt)
        generated_response = _parse_ai_response(response_text)
        
        # Merge new activities into response
        response = _merge_regenerated_field(
            previous_response=activity_session.response,
            generated_response=generated_response,
            update_field_name="tour_plan",
        )
        
        # Update activity session
        updated_session = ActivitySessionStore.update_response(
            activity_session_id=regenerate_data.activity_session_id,
            response=response,
            day_to_regenerate=regenerate_data.day_to_regenerate,
            user_instruction=regenerate_data.user_instruction or "",
        )
        
        if updated_session is None:
            raise HTTPException(status_code=404, detail="Activity session not found.")
        
        return {
            "activity_session_id": updated_session.activity_session_id,
            "city": updated_session.city,
            "tour_plan": updated_session.tour_plan,
            "response": updated_session.response,
        }
    
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# ==================== SESSION MANAGEMENT ====================

@router.get("/session/{session_id}")
async def get_session_details(session_id: str):
    """Get full session details: Q&A, suggestions, and regeneration history."""
    session = CitySessionStore.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    return {
        "session_id": session.session_id,
        "questions_answers": session.questions_answers.dict(),
        "suggested_cities": session.suggested_cities,
        "regeneration_history": session.history,
    }


@router.get("/activity_session/{activity_session_id}")
async def get_activity_session_details(activity_session_id: str):
    """Get full activity session details: city, tour plan, and regeneration history."""
    session = ActivitySessionStore.get(activity_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Activity session not found.")
    
    return {
        "activity_session_id": session.activity_session_id,
        "parent_session_id": session.parent_session_id,
        "city": session.city,
        "tour_plan": session.tour_plan,
        "regeneration_history": session.history,
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a city session and all linked activity sessions."""
    if not CitySessionStore.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    
    # Also delete all activity sessions linked to this city session
    ActivitySessionStore.delete_by_parent(session_id)
    
    return {"message": "Session and all linked activity sessions deleted successfully."}


@router.delete("/activity_session/{activity_session_id}")
async def delete_activity_session(activity_session_id: str):
    """Delete an activity session (does NOT delete parent city session)."""
    if not ActivitySessionStore.delete(activity_session_id):
        raise HTTPException(status_code=404, detail="Activity session not found.")
    
    return {"message": "Activity session deleted successfully."}