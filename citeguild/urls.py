"""citeguild URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path("reports/", include("apps.reports.urls"))
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from apps.pages.views import AccountSignupByPasskeyView, AccountSignupView
from citeguild.sitemaps import sitemaps

urlpatterns = [
    path("admin/", admin.site.urls),
]

if settings.MFA_PASSKEY_SIGNUP_ENABLED:
    urlpatterns.append(
        path(
            "accounts/signup/passkey/",
            AccountSignupByPasskeyView.as_view(),
            name="account_signup_by_passkey",
        )
    )

urlpatterns += [
    # Override allauth signup with custom views.
    path("accounts/signup/", AccountSignupView.as_view(), name="account_signup"),
    path("accounts/", include("allauth.urls")),
    path("anymail/", include("anymail.urls")),
    path("uses", TemplateView.as_view(template_name="pages/uses.html"), name="uses"),
    path("api/", include("apps.api.urls")),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path("", include("apps.mcp_server.urls")),
    path("", include("apps.pages.urls")),
    path("", include("apps.core.urls")),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
]
