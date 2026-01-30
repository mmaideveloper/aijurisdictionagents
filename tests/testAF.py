import os
from openai import AzureOpenAI

print("Testing Azure OpenAI Client")

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip() or "2024-12-01-preview"
subscription_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

if not endpoint or not deployment or not subscription_key:
    raise ValueError(
        "Missing Azure OpenAI configuration. "
        "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, and AZURE_OPENAI_API_KEY."
    )

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "I am going to Paris, what should I see?",
        }
    ],
    max_tokens=4096,
    temperature=1.0,
    top_p=1.0,
    model=deployment
)

print(response.choices[0].message.content)
