from django.urls import path

from .views import SupportTicketCreateView

urlpatterns = [
    path("support/", SupportTicketCreateView.as_view(), name="support-ticket-create"),
]
