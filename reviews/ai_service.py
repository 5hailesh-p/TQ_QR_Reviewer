import json
import random
import re

from django.conf import settings
from google import genai
from google.genai import types

# Loose sentiment guide only: the model has freedom in tone and wording,
# it just must not contradict the star rating.
SENTIMENT_BY_RATING = {
    1: "clearly unhappy but polite; point to what could be improved",
    2: "mostly unsatisfied; polite, mentions what fell short",
    3: "mixed or neutral; fair, some good and some not so good",
    4: "happy and positive; would likely recommend",
    5: "very happy and enthusiastic; would strongly recommend",
}

# Different writing styles, so the 5 reviews don't sound alike.
# 5 are picked at random for each batch.
STYLE_OPTIONS = [
    "short and punchy, 1-2 sentences",
    "friendly and casual, like talking to a friend",
    "professional and polite",
    "detailed and descriptive, mentions one or two aspects",
    "starts with the outcome or feeling, then explains why",
    "simple and direct, plain everyday words",
    "warm and appreciative, thanks the team",
    "recommendation-style, tells other people what to expect",
]


def _split_services(services_text):
    """'Web design, SEO; App development' -> ['Web design', 'SEO', 'App development']"""
    parts = re.split(r"[,;\n|]+", services_text or "")
    seen, result = set(), []
    for item in (p.strip() for p in parts):
        if item and item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
    return result


def _clean(text):
    return (text or "").strip()


def generate_review_suggestions(business, rating, experience="", previous=None):
    """
    Returns up to 5 SEO-friendly review suggestions for the business.
    - rating: 1-5 (only the sentiment must match; wording/tone is flexible)
    - experience: optional customer note
    - previous: earlier suggestions to avoid repeating
    """
    if rating not in SENTIMENT_BY_RATING:
        raise ValueError("Rating must be between 1 and 5.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    name = _clean(business.name)
    category = _clean(business.category)
    description = _clean(business.description)[:700]
    services = _split_services(business.services)

    # Keywords for this batch: category + a few services (changes every call)
    keywords = []
    if category:
        keywords.append(category)
    if services:
        keywords += random.sample(services, min(3, len(services)))

    styles = random.sample(STYLE_OPTIONS, 5)
    style_lines = "\n".join(f"  Review {i + 1}: {s}" for i, s in enumerate(styles))

    experience = _clean(experience)
    if experience:
        experience_block = (
            f'Customer\'s own words: """{experience}"""\n'
            "Base the reviews on these words and do not add facts beyond them."
        )
    else:
        experience_block = (
            "The customer gave no details. Keep reviews general: do not invent "
            "specific events, staff names, product or dish names, prices, dates or results."
        )

    avoid_block = ""
    if previous:
        recent = [p for p in previous if isinstance(p, str) and p.strip()][-10:]
        if recent:
            avoid_block = (
                "Do NOT reuse the wording or ideas of these earlier reviews:\n"
                + "\n".join(f"- {p}" for p in recent)
            )

    prompt = f"""
You write genuine-sounding Google review drafts that help a local business
rank well in search, while staying honest and natural.

BUSINESS
Name: {name}
Category: {category or "not specified"}
Services: {", ".join(services) if services else "not specified"}
About: {description or "not specified"}

Star rating: {rating}/5
Sentiment: {SENTIMENT_BY_RATING[rating]}
(The sentiment must fit the rating. Beyond that, you are free to choose
natural wording and tone.)

{experience_block}

SEO KEYWORDS FOR THIS BATCH: {", ".join(keywords) if keywords else "none"}

WRITING STYLE PER REVIEW:
{style_lines}

{avoid_block}

SEO RULES
- Mention the business name naturally in each review.
- Weave in 1 or 2 relevant keywords (category or service) as part of normal
  sentences, such as "best software company for ..." or "their SEO service ...".
  Prefer natural phrases customers would actually search for.
- Spread different keywords across the 5 reviews; never stuff or repeat keywords.
- Do not copy phrases from the business description word for word.

QUALITY RULES
- Exactly 5 reviews, each 20 to 45 words, first person, easy to edit.
- Each review must have a different opening and a different structure.
- Sound like a real customer: no marketing slogans, no "best in the city/world",
  no emojis, no hashtags.
- Never claim the customer used a specific service, bought a product or met a
  specific person unless the customer's own words say so.
- For ratings 1-3, stay polite and factual; no insults or accusations.

Return JSON: {{"suggestions": ["...", "...", "...", "...", "..."]}}
"""

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "suggestions": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["suggestions"],
            },
            temperature=1.0,
        ),
    )

    text = _clean(response.text)
    if not text:
        raise ValueError("Empty AI response")

    # Safety net in case the model wraps JSON in code fences
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    result = json.loads(text)
    suggestions = [
        s.strip()
        for s in result.get("suggestions", [])
        if isinstance(s, str) and s.strip()
    ]

    if len(suggestions) < 3:
        raise ValueError("Invalid AI response")

    return suggestions[:5]