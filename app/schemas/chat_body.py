from datetime import date
from pydantic import BaseModel
from typing import List, Optional


class QuestionAnswers(BaseModel):
    # How are you feeling today?
    todays_feeling: str

    # What kind of experience is calling to you?
    experience_kind: str

    # What's your energy like for this trip?
    energy_level: str

    # How do you want to experience this journey?
    travel_style: str

    # How would you like your trip to be organized?
    trip_organization: str

    # Are there any activities you'd like to avoid or can't do?
    activity_restrictions: list[str]

    # Which word best describes the season you're in right now?
    life_season: str

    # What environment speaks to your soul?
    preferred_environments: list[str]

    # Your birthdate
    birthdate: date

    # Approximate budget per person/night
    budget_per_person_per_night: float

    # How many days are you planning to travel?
    trip_length_days: int

class InputData(BaseModel):
    questions_answers: QuestionAnswers
    preferred_destinations: Optional[str] = None
    hope_of_this_trip: str


class RegenerateInputData(BaseModel):
    session_id: str
    user_instraction: str

                     