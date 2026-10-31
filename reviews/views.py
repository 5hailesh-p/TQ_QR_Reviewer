import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from businesses.models import Business

from .models import ReviewActivity, SuggestionPool, make_text_hash
from .suggestion_service import get_review_suggestions

logger = logging.getLogger(__name__)


def _is_json(request):
    return (request.content_type or "").startswith("application/json")


def _get_data(request):
    """Works with both JSON bodies and FormData / form-encoded posts."""
    if _is_json(request):
        try:
            data = json.loads(request.body or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return request.POST


def _get_previous(request, data):
    if _is_json(request):
        previous = data.get("previous", [])
    else:
        previous = request.POST.getlist("previous")
    if not isinstance(previous, list):
        return []
    return [p for p in previous if isinstance(p, str)][:30]


@ensure_csrf_cookie
def review_page(request, slug):
    business = get_object_or_404(Business, slug=slug)
    return render(request, "reviews/review_page.html", {"business": business})


@require_POST
def generate_ai_reviews(request, slug):
    business = get_object_or_404(Business, slug=slug)
    data = _get_data(request)

    try:
        rating = int(data.get("rating", 0))
    except (ValueError, TypeError):
        rating = 0

    if rating not in range(1, 6):
        return JsonResponse(
            {"success": False, "message": "Please select a star rating."},
            status=400,
        )

    experience = (data.get("experience") or "").strip()
    if len(experience) > 1000:
        return JsonResponse(
            {"success": False, "message": "Your note is too long."},
            status=400,
        )

    previous = _get_previous(request, data)

    try:
        suggestions = get_review_suggestions(
            business=business,
            rating=rating,
            experience=experience,
            previous=previous,
        )
    except Exception:
        logger.exception("Review suggestion generation failed")
        return JsonResponse(
            {
                "success": False,
                "message": "Unable to generate suggestions. Please try again.",
            },
            status=503,
        )

    activity = ReviewActivity.objects.create(
        business=business,
        rating=rating,
        experience=experience,
        ai_suggestions=suggestions,
    )

    return JsonResponse(
        {
            "success": True,
            "activity_id": activity.id,
            "suggestions": suggestions,
        }
    )


@require_POST
def select_review(request, slug):
    """
    Saves the final review and marks the chosen AI suggestion as used,
    so it is not shown to other customers again.
    Expects: activity_id, review (final edited text), suggestion (original AI text).
    """
    business = get_object_or_404(Business, slug=slug)
    data = _get_data(request)

    try:
        activity_id = int(data.get("activity_id"))
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "message": "Invalid activity."},
            status=400,
        )

    activity = get_object_or_404(ReviewActivity, id=activity_id, business=business)

    activity.selected_review = (data.get("review") or "").strip()[:5000]
    activity.save(update_fields=["selected_review"])

    original = (data.get("suggestion") or "").strip()
    if original and activity.rating:
        SuggestionPool.objects.filter(
            business=business,
            rating=activity.rating,
            text_hash=make_text_hash(original),
        ).update(is_used=True, used_at=timezone.now())

    return JsonResponse(
        {"success": True, "redirect_url": business.google_review_url}
    )