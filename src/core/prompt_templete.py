from typing import List, Optional
from app.schemas.city_body import QuestionAnswers, CitySuggestionInput, TourPlanDayInput


class PromptGenerator:
    """Generate profile-led wellness journey prompts without changing output schemas."""

    ARCHETYPE_REFERENCE = """
- Burned-Out Achiever: needs nervous-system regulation, quiet, and sleep; avoid pressure and forced socializing.
- Transformer: needs structure, accountability, and safe physical engagement; avoid passive programming.
- Seeker: needs mindfulness, nature, meaning, and grounding; avoid clinical/data-heavy experiences.
- Optimizer: needs diagnostics, longevity, and measurable outcomes; avoid vague offerings.
- Escapist: needs beauty, simplicity, freedom, and sensory reset; avoid intensity and rigid groups.
- Reconnector: needs warmth, intimacy, shared experience, and soft structure; avoid isolating or cold settings.
"""

    BUDGET_TIER_REFERENCE = """
Entry = USD 30-150, Premium = USD 150-400, Luxury = USD 400-1,000,
Ultra Luxury = USD 1,000+ per person/night.
"""
    # ==================== CITY SUGGESTION PROMPTS ====================
    @staticmethod
    def gen_city_suggestion_prompt(
        questions_answers: QuestionAnswers,
        preferred_destinations: Optional[str] = None,
        hope_of_this_trip: str = "",
    ) -> str:
        """
        Generate prompt to suggest cities based on user's Q&A.
        First time flow: User answers all questions -> AI recommends best cities.
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()
        preferred_region = questions_answers.preferred_region or preferred_destinations
        additional_context = ""
        if preferred_region:
            additional_context += f"\nPreferred region (hard constraint): {preferred_region}"
        if hope_of_this_trip:
            additional_context += f"\nWhat they hope to achieve: {hope_of_this_trip}"
        prompt = f"""
            Design a restorative or transformative wellness journey, not a generic tourist
            recommendation. Interpret all 12 answers together, infer a primary and optional
            secondary traveler archetype internally, then suggest the 3-5 BEST destinations.
            USER PROFILE:
            {qa_summary}
            {additional_context}
            ARCHETYPE REFERENCE (from Archetype Reference.xlsx):
            {PromptGenerator.ARCHETYPE_REFERENCE}
            BUDGET REFERENCE (from Budget Tier Legend.xlsx):
            {PromptGenerator.BUDGET_TIER_REFERENCE}
            Match against Retreat Master Database dimensions such as emotional tone, structure,
            spirituality, physical intensity, transformation focus, emotional safety, nature,
            modalities, archetype/solo/couple/beginner fit, nightly price, and program cost.
            {tool_usage_rules}
            REQUIREMENTS:
            1. Start with the desired emotional outcome, then match tone, pace, structure,
               environment, safe intensity, and season of life; do not merely match keywords.
            2. Treat activity restrictions and a supplied preferred region as hard constraints.
            3. Use the per-person/night budget tier and {questions_answers.trip_length_days}-day duration;
               reject destinations that are financially implausible.
            4. Use age only for pace, accessibility, and suitability; never stereotype.
            5. Use tools with a dynamic profile search query, never a location-only generic query.
            6. Keep the exact output template and do not expose archetype or scoring fields.
            7. For each city, provide its real country name (to be verified).
            RESPONSE FORMAT (JSON ONLY):
            {{
                "suggested_cities": [
                    {{
                        "city_name": "City Name",
                        "country_name": "Country",
                        "number_of_days": <recommended number of days>,
                        "description": "<1-2 sentence explanation of why this city matches their profile>"
                    }}
                ]
            }}
            Respond ONLY with valid JSON, no preamble.
            """
        return prompt
    @staticmethod
    def regenerate_city_suggestion_prompt(
        questions_answers: QuestionAnswers,
        previous_suggestions: List[CitySuggestionInput],
        user_instruction: str = "",
    ) -> str:
        """
        Generate prompt to get different city suggestions.
        Regenerate flow: Keep Q&A, suggest different cities (exclude previous ones).
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()
        previous_cities = ", ".join([c.city_name for c in previous_suggestions])
        instruction_context = ""
        if user_instruction:
            instruction_context = f"\nUser's additional instruction: {user_instruction}"
        prompt = f"""
Redesign the wellness journey rather than producing a generic city list. The user previously received:
{previous_cities}
Now, provide 3-5 DIFFERENT cities that still match their profile.
USER PROFILE:
{qa_summary}
{instruction_context}
{tool_usage_rules}
IMPORTANT:
1. Do NOT repeat: {previous_cities}
2. Re-evaluate the complete emotional and experiential profile, not only the new instruction.
3. Match tone, structure, intensity, nature, safety, budget tier, duration, and region.
4. Treat restrictions and a supplied region as hard constraints.
5. Use dynamic profile-led tool search queries.
6. For each city, provide its real country name (to be verified).
RESPONSE FORMAT (JSON ONLY):
{{
    "suggested_cities": [
        {{
            "city_name": "City Name",
            "country_name": "Country",
            "number_of_days": <recommended days>,
            "description": "<1-2 sentence explanation>"
        }}
    ]
}}
Respond ONLY with valid JSON, no preamble.
"""
        return prompt
    # ==================== TOUR PLAN / ACTIVITY PROMPTS ====================
    @staticmethod
    def gen_tour_plan_prompt(
        questions_answers: QuestionAnswers,
        selected_city: str,
        trip_length_days: int,
    ) -> str:
        """
        Generate prompt for day-wise activity itinerary.
        Generate flow: User selected a city -> AI creates day-by-day activities.
        The LLM only proposes activity names, descriptions, areas, times, and costs.
        Addresses, images, distances, and hotel info will be filled in by a separate tool step.
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        prompt = f"""
Design a {trip_length_days}-day restorative or transformative wellness journey in {selected_city}, not a checklist of tourist sights.
USER PROFILE:
{qa_summary}
REQUIREMENTS:
1. Create {trip_length_days} days of activities.
2. Match their travel style: {questions_answers.travel_style}
3. Fit their energy level: {questions_answers.energy_level}
4. Stay within the effective one-person trip budget: ${questions_answers.effective_total_budget:.2f}.
5. AVOID these activities: {', '.join(questions_answers.activity_restrictions)}
6. Prefer these environments: {', '.join(questions_answers.preferred_environments)}
7. Every activity must advance the desired emotional outcome and match the traveler's safe intensity and preferred structure.
8. Use dynamic tool queries combining activity intent, profile needs, environment, and city.
9. For each sightseeing/activity stop, provide ONLY the activity name, a short description, the rough area/neighborhood in the city,
   a suggested time window, and an estimated cost in USD.
10. Do not repeat the same attraction/place on multiple days; distribute unique places across the full itinerary.
11. Do NOT include breakfast, lunch, or dinner stops. The system will add those as verified restaurant activities later.
CRITICAL - Do NOT invent or include these fields. They will be filled by a real data tool later:
   - Do NOT include an exact street address (no "activity_address" field)
   - Do NOT include any image URLs (no "activity_image" field)
   - Do NOT include any distance values (no "distance_from_previous_km" field)
   Only the fields listed in the RESPONSE FORMAT below should be included.
RESPONSE FORMAT (JSON ONLY):
{{
    "tour_plan": [
        {{
            "day": 1,
            "activities": [
                {{
                    "activity_name": "Activity Name",
                    "activity_description": "What you'll do",
                    "activity_location": "Exact location in city",
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>
                }}
            ]
        }}
    ],
    "total_cost_estimate": <sum of all activity costs across all days>,
    "packing_tips": "<Brief packing advice for this city>",
    "travel_tips": "<Brief travel advice>"
}}
Respond ONLY with valid JSON, no preamble.
"""
        return prompt
    @staticmethod
    def regenerate_tour_plan_prompt(
        questions_answers: QuestionAnswers,
        city_name: str,
        current_tour_plan: List[TourPlanDayInput],
        day_to_regenerate: Optional[int] = None,
        user_instruction: str = "",
    ) -> str:
        """
        Generate prompt to get different activities.
        Regenerate flow: Keep city, regenerate activities (all or single day).
        The LLM only proposes activity names, descriptions, areas, times, and costs.
        Addresses, images, distances, and hotel info will be filled in by a separate tool step.
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        scope = f"Day {day_to_regenerate}" if day_to_regenerate else "the entire itinerary"
        instruction_context = ""
        if user_instruction:
            instruction_context = f"\nUser's request: {user_instruction}"
        current_plan_summary = PromptGenerator._build_plan_summary(current_tour_plan)
        prompt = f"""
You are an expert tour planner. Regenerate activities for {city_name}.
Previously suggested itinerary:
{current_plan_summary}
Now provide DIFFERENT activities for {scope} while keeping the rest the same.
USER PROFILE:
{qa_summary}
{instruction_context}
REQUIREMENTS:
1. Match travel style: {questions_answers.travel_style}
2. Match energy level: {questions_answers.energy_level}
3. Stay within the effective one-person trip budget: ${questions_answers.effective_total_budget:.2f}.
4. AVOID: {', '.join(questions_answers.activity_restrictions)}
5. For each sightseeing/activity stop, provide ONLY the activity name, a short description, the rough area/neighborhood,
   a suggested time window, and an estimated cost in USD.
6. Do not repeat attractions already present in the itinerary unless the user explicitly asked for that place.
7. Do NOT include breakfast, lunch, or dinner stops. The system will add those as verified restaurant activities later.
CRITICAL - Do NOT invent or include these fields. They will be filled by a real data tool later:
   - Do NOT include an exact street address (no "activity_address" field)
   - Do NOT include any image URLs (no "activity_image" field)
   - Do NOT include any distance values (no "distance_from_previous_km" field)
   Only the fields listed in the RESPONSE FORMAT below should be included.
RESPONSE FORMAT (JSON ONLY):
{{
    "tour_plan": [
        {{
            "day": <day number>,
            "activities": [
                {{
                    "activity_name": "Different Activity Name",
                    "activity_description": "What you'll do",
                    "activity_location": "Exact location",
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>
                }}
            ]
        }}
    ],
    "reasoning": "<Why these are good alternatives>"
}}
Respond ONLY with valid JSON, no preamble.
"""
        return prompt
    # ==================== HELPER METHODS ====================
    @staticmethod
    def _build_tool_usage_guidance() -> str:
        """Return explicit profile-led tool-use and image guidance."""
        return """
TOOL USAGE:
1. Call tools for real cities, stays, activities, restaurants, routes, and images.
2. Build a concise dynamic `search_query` from desired outcome, archetype needs, energy,
   environment, organization style, budget tier, and region. Do not search by location alone.
3. Put positive needs in the query; filter restrictions after retrieval instead of searching avoided terms.
4. Never invent or alter place data or photo IDs. The API layer resolves compact photo IDs.
"""
    @staticmethod
    def _build_qa_summary(qa: QuestionAnswers) -> str:
        """Build human-readable summary of Q&A."""
        budget_line = (
            f"${qa.budget_per_person_per_night:.2f} per person/night "
            f"(${qa.effective_total_budget:.2f} for one traveler)"
            if qa.budget_per_person_per_night is not None
            else f"${qa.effective_total_budget:.2f} total (legacy input)"
        )
        return f"""
- Current feeling: {qa.todays_feeling}
- Desired experience: {qa.experience_kind}
- Energy level: {qa.energy_level}
- Travel style: {qa.travel_style}
- Trip organization preference: {qa.trip_organization}
- Restricted activities: {', '.join(qa.activity_restrictions) if qa.activity_restrictions else 'None'}
- Season of life: {qa.life_season}
- Preferred environments: {', '.join(qa.preferred_environments)}
- Age (from birthdate): {PromptGenerator._calculate_age(qa.birthdate)}
- Trip budget: {budget_line}
- Trip duration: {qa.trip_length_days} days
- Preferred region: {qa.preferred_region or 'No region constraint supplied'}
"""
    @staticmethod
    def _build_plan_summary(tour_plan: List[TourPlanDayInput]) -> str:
        """Build human-readable summary of current tour plan."""
        summary = ""
        for day_plan in tour_plan:
            summary += f"\nDay {day_plan.day}:\n"
            for activity in day_plan.activities:
                summary += f"  - {activity.activity_name} ({activity.activity_time}) @ {activity.activity_location} (${activity.activity_cost})\n"
        return summary
    @staticmethod
    def _calculate_age(birthdate) -> int:
        """Calculate age from birthdate."""
        from datetime import date
        today = date.today()
        return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
