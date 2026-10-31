from django.db import models
from django.utils.text import slugify

# Create your models here.


class Business(models.Model):

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)

    category = models.CharField(
        max_length=100,
        blank=True
    )

    services = models.TextField(
        blank=True,
        help_text="Comma-separated business services"
    )

    logo = models.ImageField(
        upload_to='business/logos',
        blank=True,
        null=True
    )

    google_review_url = models.URLField()
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
 
