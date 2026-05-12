from aijurisdictionagents.agents.audio_action_tools import AIAudioToolRecognizerAgent

agent = AIAudioToolRecognizerAgent()
for text in [
    "vytvor pripad splnomocnenie",
    "I want to validate company",
    "validate car vin WAUZZZ8K4DA123456",
]:
    result = agent.recognize(text)
    print(text, "=>", result)
