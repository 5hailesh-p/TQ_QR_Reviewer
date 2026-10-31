import logging

from django.db.models import F

from .ai_service import generate_review_suggestions
from .models import SuggestionPool, make_text_hash

logger = logging.getLogger(__name__)

SUGGESTIONS_PER_REQUEST = 5


def _available(business, rating, exclude_texts):
    """Unused saved reviews for this business + rating."""
    qs = SuggestionPool.objects.filter(
        business=business, rating=rating, is_used=False
    )
    if exclude_texts:
        qs = qs.exclude(text_hash__in=[make_text_hash(t) for t in exclude_texts])
    return qs


def _pick(business, rating, exclude_texts):
    # least-shown first, random among equals
    return list(
        _available(business, rating, exclude_texts)
        .order_by("times_shown", "?")[:SUGGESTIONS_PER_REQUEST]
    )


def get_review_suggestions(business, rating, experience="", previous=None):
    """
    1. Customer typed their own note -> always call the API (personalised, not saved).
    2. Otherwise use saved reviews; call the API only if fewer than 5 are available.
    """
    previous = [p for p in (previous or []) if isinstance(p, str)]
    experience = (experience or "").strip()

    if experience:
        return generate_review_suggestions(business, rating, experience, previous)

    chosen = _pick(business, rating, previous)

    if len(chosen) < SUGGESTIONS_PER_REQUEST:
        try:
            recent_pool_texts = list(
                SuggestionPool.objects.filter(business=business, rating=rating)
                .order_by("-id")
                .values_list("text", flat=True)[:10]
            )
            new_texts = generate_review_suggestions(
                business, rating, "", recent_pool_texts + previous
            )
            SuggestionPool.objects.bulk_create(
                [
                    SuggestionPool(
                        business=business,
                        rating=rating,
                        text=t,
                        text_hash=make_text_hash(t),
                    )
                    for t in new_texts
                ],
                ignore_conflicts=True,  # skips exact duplicates
            )
        except Exception:
            logger.exception("AI call failed while refilling the review pool")
            if not chosen:
                raise  # nothing saved to fall back on
            # otherwise serve whatever saved reviews we have

        chosen = _pick(business, rating, previous)

    if not chosen:
        raise ValueError("No review suggestions available")

    SuggestionPool.objects.filter(id__in=[c.id for c in chosen]).update(
        times_shown=F("times_shown") + 1
    )
    return [c.text for c in chosen]