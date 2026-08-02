from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


def subscription_required(view_func):
    """Require Stripe-confirmed paid access for server-side product views."""

    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.profile.has_active_subscription:
            return redirect("pricing")
        return view_func(request, *args, **kwargs)

    return wrapped


class ActiveSubscriptionRequiredMixin(LoginRequiredMixin):
    """Reusable paywall for future site-management class-based views."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.profile.has_active_subscription:
            return redirect("pricing")
        return super().dispatch(request, *args, **kwargs)
