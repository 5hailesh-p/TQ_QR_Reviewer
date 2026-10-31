import hashlib

from django.db import models
from businesses.models import Business


def make_text_hash(text):
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


class ReviewActivity(models.Model):

    RATING_CHOICE = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='review_activities'
    )

    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICE,
        null=True,
        blank=True
    )

    experience = models.TextField(blank=True)

    ai_suggestions = models.JSONField(
        default=list,
        blank=True
    )

    selected_review = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.rating} Stars"


class SuggestionPool(models.Model):
    """Saved AI reviews, reused so we don't call the API every time."""

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='suggestion_pool'
    )
    rating = models.PositiveSmallIntegerField(db_index=True)
    text = models.TextField()
    text_hash = models.CharField(max_length=64, editable=False)

    times_shown = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)  # customer picked it

    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'rating', 'text_hash'],
                name='unique_pool_review_per_business_rating',
            )
        ]
        indexes = [
            models.Index(fields=['business', 'rating', 'is_used']),
        ]

    def save(self, *args, **kwargs):
        self.text_hash = make_text_hash(self.text)
        super().save(*args, **kwargs)

    def __str__(self):
        status = "used" if self.is_used else "available"
        return f"{self.business.name} - {self.rating}★ ({status})"