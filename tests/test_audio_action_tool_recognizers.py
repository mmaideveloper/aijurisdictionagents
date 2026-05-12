from aijurisdictionagents.agents.audio_action_tools import AIAudioToolRecognizerAgent, AIActionToolRecognizerAgent


def test_audio_recognizes_create_case():
    result = AIAudioToolRecognizerAgent().recognize('vytvor pripad')
    assert result and result.tool_name == 'CreateCase'


def test_action_company_calls_existing_agent_prompt():
    result = AIActionToolRecognizerAgent().recognize('I want to validate company ACME s.r.o.')
    assert result and result.tool_name == 'ValidationCompany'
    assert 'search_prompt' in (result.result or {})


def test_action_car_calls_existing_agent_plan():
    result = AIActionToolRecognizerAgent().recognize('validate car vin WAUZZZ8K4DA123456')
    assert result and result.tool_name == 'ValidationCar'
    assert ((result.result or {}).get('plan') or {}).get('mode') in {'vin', 'vin+spz', 'spz'}
