from fastapi import APIRouter, HTTPException
from src.core.prompt_templete import PromptGenerator
from src.service.chat_services import get_ai_response
from app.schemas.city_body import (
    InputData,
    RegenerateInputData,
    RegenerateActivityInputData,
    TourPlanRequestData,
)
from src.core.data_processor import ProcessData
from src.session.city_session_store import CitySessionStore, ActivitySessionStore
from src.tools.tools import get_cityinfo

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


def _enrich_city_suggestions(suggested_cities: list) -> list:
    """
    Enrich LLM-proposed city suggestions with real data from get_cityinfo tool.
    
    For each city in the list:
    1. Call get_cityinfo with the city name
    2. Merge the tool's verified country, lat, lng, and photos list into the city dict
    3. If the tool errors, fall back to empty image list and null coordinates
    
    The LLM output should never contain city_image, latitude, or longitude —
    those are supplied entirely by this enrichment step.
    """
    enriched = []
    for city in suggested_cities:
        city_name = city.get("city_name", "")
        if not city_name:
            continue
        
        # Default values in case tool fails
        tool_country = None
        tool_photos = []
        tool_lat = None
        tool_lng = None
        
        try:
            result = get_cityinfo.invoke({"city_name": city_name})
            if result and "error" not in result:
                tool_country = result.get("country")
                tool_photos = result.get("photos", [])
                # Ensure photos is always a clean list[str]:
                # - tool returns ["No photos available"] sentinel when none exist → replace with []
                # - also guard against bare-string edge case
                if not isinstance(tool_photos, list):
                    tool_photos = []
                else:
                    # Filter out the "No photos available" sentinel
                    tool_photos = [p for p in tool_photos if p != "No photos available"]
                location = result.get("lat")
                if location is not None:
                    tool_lat = float(location)
                location = result.get("lng")
                if location is not None:
                    tool_lng = float(location)
        except Exception:
            # Tool failure — keep defaults (empty photos, null coords)
            pass
        
        # country_name priority: tool's verified value > LLM's guess
        merged_country = tool_country if tool_country else city.get("country_name")
        
        enriched.append({
            "city_name": city_name,
            "country_name": merged_country,
            "city_image": tool_photos,
            "latitude": tool_lat,
            "longitude": tool_lng,
            "number_of_days": city.get("number_of_days"),
            "description": city.get("description", ""),
        })
    
    return enriched


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
        
        # Enrich LLM suggestions with real data from get_cityinfo tool
        raw_cities = response.get("suggested_cities", [])
        enriched_cities = _enrich_city_suggestions(raw_cities)
        # Replace LLM-only output with enriched version in the response dict
        response["suggested_cities"] = enriched_cities
        
        # Create session and store Q&A + enriched suggestions
        session = CitySessionStore.create(
            questions_answers=input_data.questions_answers,
            suggested_cities=enriched_cities,
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
        
        # Enrich new LLM suggestions with real data from get_cityinfo tool
        raw_cities = generated_response.get("suggested_cities", [])
        enriched_cities = _enrich_city_suggestions(raw_cities)
        generated_response["suggested_cities"] = enriched_cities
        
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
async def get_tour_plan(request_data: TourPlanRequestData):
    """
    GENERATE: First time → create day-wise activity plan for selected city.
    - Creates separate activity session (linked to city session).
    - Stores generated activities in session.
    - Returns activity_session_id for future regenerate calls.
    """
    # Fetch parent city session
    city_session = CitySessionStore.get(request_data.session_id)
    if city_session is None:
        raise HTTPException(status_code=404, detail="City session not found.")
    
    try:
        # Check if activity session already exists for this city (to avoid re-generation)
        activity_session = ActivitySessionStore.get_by_city(
            session_id=request_data.session_id,
            city_name=request_data.selected_city,
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
            selected_city=request_data.selected_city,
            trip_length_days=city_session.questions_answers.trip_length_days,
        )
        
        response_text = get_ai_response(prompt)
        response = _parse_ai_response(response_text)
        
        # Create new activity session
        activity_session = ActivitySessionStore.create(
            parent_session_id=request_data.session_id,
            city_name=request_data.selected_city,
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
        "questions_answers": session.questions_answers.model_dump(),
        "suggested_cities": [city.model_dump() for city in session.suggested_cities],
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
        "tour_plan": [day.model_dump() for day in session.tour_plan],
        "regeneration_history": session.history,
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a city session and all linked activity sessions."""
    if not CitySessionStore.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")

    ActivitySessionStore.delete_by_parent(session_id)

    return {"message": "Session and all linked activity sessions deleted successfully."}


@router.delete("/activity_session/{activity_session_id}")
async def delete_activity_session(activity_session_id: str):
    """Delete an activity session (does NOT delete parent city session)."""
    if not ActivitySessionStore.delete(activity_session_id):
        raise HTTPException(status_code=404, detail="Activity session not found.")

    return {"message": "Activity session deleted successfully."}