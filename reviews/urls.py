from django.urls import path
from . import views

urlpatterns = [
    path("<slug:slug>/", views.review_page, name="review_page"),
    path("<slug:slug>/generate/", views.generate_ai_reviews, name="generate_ai_reviews"),
    path("<slug:slug>/select/", views.select_review, name="select_review"),
    
]
