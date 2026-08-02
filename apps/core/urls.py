from django.urls import path

from apps.core import views

urlpatterns = [
    # App pages
    path("AGENTS.md", views.agent_instructions_markdown, name="agent_instructions_markdown"),
    path("home", views.HomeView.as_view(), name="home"),
    path("settings", views.UserSettingsView.as_view(), name="settings"),
    path("admin-panel", views.AdminPanelView.as_view(), name="admin_panel"),
    # Utils
    path("settings/api-key/rotate/", views.rotate_api_key, name="rotate_api_key"),
    path(
        "sites/<uuid:project_uuid>/retry-sync/",
        views.retry_site_sync,
        name="retry_site_sync",
    ),
    path("resend-confirmation/", views.resend_confirmation_email, name="resend_confirmation"),
    path("delete-account/", views.delete_account, name="delete_account"),
    # Payments
    path("stripe-webhook/", views.stripe_webhook, name="stripe_webhook"),
    path(
        "create-checkout-session/",
        views.create_checkout_session,
        name="user_upgrade_checkout_session",
    ),
    path(
        "create-customer-portal/",
        views.create_customer_portal_session,
        name="create_customer_portal_session",
    ),
]
