from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from typing import List

from datetime import date

class QuestionAnswers():

    todays_feeling: str

    experience_kind: str

    energy_level: str

    travel_style: str

    trip_organization: str

    activity_restrictions: list[str]
    life_season: str

    preferred_environments: list[str]

    birthdate: date

    budget_per_person_per_night: float
    trip_length_days: int



@dataclass
class CitySuggestion:
    city_name: str
    country_name: str
    number_of_days: int


@dataclass
class TourPlanActivity:
    activity_name: str
    activity_description: str
    activity_location: str
    activity_time: str
    activity_cost: float

@dataclass
class TourPlanDay():
    day: int
    activities: List[TourPlanActivity]




@dataclass
class CitySuggestionResponse():
    questions_answers: QuestionAnswers
    suggested_cities: List[CitySuggestion]

@dataclass
class TourPlanResponse():
    questions_answers: QuestionAnswers
    suggested_citie: CitySuggestion
    suggested_tour_plan: List[TourPlanDay]


class CitySessionStore:
    _sessions: dict[str, CitySuggestionResponse] = {}

    @classmethod
    def create(cls, questions_answers, suggested_cities, response ) -> CitySuggestionResponse:
        session_id = str(uuid4())
        session =  CitySuggestionResponse(
                session_id=session_id,
                questions_answers=questions_answers,
                suggested_cities=suggested_cities)
        history = [{
            "action": "generated city suggestions",
            "response": deepcopy(response),
            "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        )
        cls._sessions[session_id] = session
        return deepcopy(session)

    @classmethod
    def get(cls, session_id: str) -> CitySessionStore | None:
        session = cls._sessions.get(session_id)
        if session is None:
            return None
        return deepcopy(session)

    @classmethod
    def update_response(
        cls,
        session_id: str,
        response: dict[str, Any],
        update_field_name: str,
        user_instruction: str,
    ) -> CitySessionStore | None:
        session = cls._sessions.get(session_id)
        if session is None:
            return None

        session.response = deepcopy(response)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        session.history.append(
            {
                "action": "regenerate",
                "update_field_name": update_field_name,
                "user_instruction": user_instruction,
                "response": deepcopy(response),
                "created_at": session.updated_at,
            }
        )
        return deepcopy(session)

    @classmethod
    def delete(cls, session_id: str) -> bool:
        return cls._sessions.pop(session_id, None) is not None
