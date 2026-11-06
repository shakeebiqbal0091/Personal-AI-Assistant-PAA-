
import json

from app.intelligence.intent_models import (
    IntentResult,
    IntentType,
)

from app.intelligence.intent_prompts import (
    INTENT_CLASSIFICATION_PROMPT,
)


class IntentClassifier:

    def __init__(self, client, model: str):

        self.client = client
        self.model = model

    def classify(
        self,
        user_message: str,
        conversation_context: str = ""
    ) -> IntentResult:

        user_message = user_message.strip()

        if not user_message:
            raise ValueError(
                "Message cannot be empty."
            )

        response = self.client.chat.completions.create(
            model=self.model,

            messages=[
                {
                    "role": "system",
                    "content": INTENT_CLASSIFICATION_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "message": user_message,
                        "conversation_context": conversation_context,
                    }),
                },
            ],

            response_format={
                "type": "json_object"
            },

            temperature=0,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Intent classifier returned an empty response."
            )

        try:
            data = json.loads(content)

            return IntentResult.model_validate(data)

        except (json.JSONDecodeError, ValueError) as error:

            raise RuntimeError(
                "Invalid intent classification response."
            ) from error