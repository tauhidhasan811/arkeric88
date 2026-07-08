import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import main
from src.service.chat_services import get_ai_response


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_cityinfo", "args": {"city_name": "Paris"}, "id": "call-1"}
                ],
            )
        return AIMessage(
            content='{"suggested_cities":[{"city_name":"Paris","country_name":"France","city_image":["https://example.com/paris.jpg"],"latitude":48.8566,"longitude":2.3522,"number_of_days":3,"description":"Romantic"}],"reasoning":"done"}'
        )


class TravelPlannerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.responses = iter([
            '{"suggested_cities":[{"city_name":"Paris","country_name":"France","number_of_days":3,"description":"Romantic"}],"reasoning":"first"}',
            '{"suggested_cities":[{"city_name":"Tokyo","country_name":"Japan","number_of_days":4,"description":"Energetic"}],"reasoning":"second"}',
            '{"tour_plan":[{"day":1,"activities":[{"activity_name":"Museum","activity_description":"Visit","activity_location":"Louvre","activity_time":"10:00","activity_cost":20}]}],"total_cost_estimate":20,"packing_tips":"light","travel_tips":"walk"}',
            '{"tour_plan":[{"day":1,"activities":[{"activity_name":"Cafe","activity_description":"Coffee","activity_location":"Center","activity_time":"11:00","activity_cost":10}]}],"reasoning":"updated"}',
        ])

    def test_get_ai_response_executes_tool_calls(self) -> None:
        fake_llm = FakeLLM()

        with patch("src.service.chat_services.GetOpenAILlm", return_value=fake_llm), patch(
            "src.service.chat_services.get_cityinfo.invoke", return_value={"photos": ["https://example.com/paris.jpg"]}
        ) as tool_mock:
            response = get_ai_response("Suggest a city")

        self.assertIn("Paris", response)
        self.assertEqual(fake_llm.calls, 2)
        tool_mock.assert_called_once_with({"city_name": "Paris"})

    def test_city_and_tour_session_flow(self) -> None:
        def fake_ai(prompt: str) -> str:
            return next(self.responses)

        with patch("app.router.city_content_route.get_ai_response", side_effect=fake_ai), patch(
            "app.router.city_content_route.get_cityinfo"
        ) as mock_tool:
            mock_tool.invoke.return_value = {
                "city_name": "MockCity",
                "country": "Mockland",
                "lat": 46.0,
                "lng": 2.0,
                "photos": ["https://example.com/photo.jpg"],
            }
            initial = self.client.post(
                "/get_suggested_city",
                json={
                    "questions_answers": {
                        "todays_feeling": "curious",
                        "experience_kind": "culture",
                        "energy_level": "medium",
                        "travel_style": "slow",
                        "trip_organization": "loose",
                        "activity_restrictions": ["crowds"],
                        "life_season": "exploration",
                        "preferred_environments": ["cities", "parks"],
                        "birthdate": "1990-01-01",
                        "budget_per_person_per_night": 120.0,
                        "trip_length_days": 3,
                    },
                    "preferred_destinations": "europe",
                    "hope_of_this_trip": "relax",
                },
            )
            self.assertEqual(initial.status_code, 200)
            session_id = initial.json()["session_id"]

            regenerated = self.client.post(
                "/regenerate_suggested_city",
                json={"session_id": session_id, "user_instruction": "more energetic"},
            )
            self.assertEqual(regenerated.status_code, 200)
            self.assertEqual(regenerated.json()["suggested_cities"][0]["city_name"], "Tokyo")

            plan = self.client.post(
                "/get_tour_plan",
                json={"session_id": session_id, "selected_city": "Paris"},
            )
            self.assertEqual(plan.status_code, 200)
            self.assertEqual(plan.json()["source"], "generated")

            plan_regenerated = self.client.post(
                "/regenerate_tour_plan",
                json={
                    "activity_session_id": plan.json()["activity_session_id"],
                    "day_to_regenerate": 1,
                    "user_instruction": "more relaxed",
                },
            )
            self.assertEqual(plan_regenerated.status_code, 200)
            self.assertEqual(plan_regenerated.json()["tour_plan"][0]["activities"][0]["activity_name"], "Cafe")

            details = self.client.get(f"/session/{session_id}")
            self.assertEqual(details.status_code, 200)
            self.assertEqual(len(details.json()["suggested_cities"]), 1)


if __name__ == "__main__":
    unittest.main()
