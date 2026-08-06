from django.urls import path

from apps.pages import views

urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
    path("privacy-policy", views.PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms-of-service", views.TermsOfServiceView.as_view(), name="terms_of_service"),
    path("pricing", views.PricingView.as_view(), name="pricing"),
    path(
        "for/saas-link-building",
        views.SaasLinkBuildingView.as_view(),
        name="saas_link_building",
    ),
    path("blog/", views.blog_posts_view, name="blog_posts"),
    path("blog/<slug:slug>", views.blog_post_view, name="blog_post"),
    path("docs/", views.docs_home_view, name="docs_home"),
    path("docs/<str:category>/<str:page>/", views.docs_page_view, name="docs_page"),
]
