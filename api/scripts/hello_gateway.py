"""Gateway smoke test.

Runs a single extractor-profile call through the gateway. On success:

- Confirms that the Groq credentials, model routing, and Langfuse
  instrumentation are all functional.
- Prints the parsed structured result on stdout.
- Emits one traced generation to the Langfuse UI containing the prompt,
  token counts, latency, and model identifier.

Usage from inside the api container:

    docker exec welyne-api python -m scripts.hello_gateway
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.gateway import llm_call


class CandidateName(BaseModel):
    full_name: str = Field(description="Extracted candidate name.")


def main() -> None:
    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured facts from short candidate blurbs. "
                'Return JSON matching the schema: {"full_name": string}. '
                "Do not include any commentary."
            ),
        },
        {
            "role": "user",
            "content": "Ahmed Ben Ali, software engineer based in Tunis.",
        },
    ]

    result = llm_call(profile="extractor", messages=messages, schema=CandidateName)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
