from django.urls import path

from apps.core import views

urlpatterns = [
    # App pages
    path("AGENTS.md", views.agent_instructions_markdown, name="agent_instructions_markdown"),
    path("home", views.HomeView.as_view(), name="home"),
    path("home/agent-setup-prompt/", views.agent_setup_prompt, name="agent_setup_prompt"),
    path("sites/<uuid:project_uuid>/", views.sitemap_details, name="sitemap_details"),
    path(
        "sites/<uuid:project_uuid>/pages/",
        views.sitemap_articles,
        name="sitemap_articles",
    ),
    path(
        "sites/<uuid:project_uuid>/links/",
        views.sitemap_links,
        name="sitemap_links",
    ),
    path(
        "sites/<uuid:project_uuid>/update/",
        views.update_sitemap,
        name="update_sitemap",
    ),
    path(
        "sites/<uuid:project_uuid>/delete/",
        views.delete_sitemap,
        name="delete_sitemap",
    ),
    path("settings", views.UserSettingsView.as_view(), name="settings"),
    path("admin-panel", views.AdminPanelView.as_view(), name="admin_panel"),
    # Utils
    path("settings/api-key/rotate/", views.rotate_api_key, name="rotate_api_key"),
    path(
        "sites/<uuid:project_uuid>/retry-sync/",
        views.retry_site_sync,
        name="retry_site_sync",
    ),
    path(
        "sites/<uuid:project_uuid>/rename/",
        views.rename_site,
        name="rename_site",
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
