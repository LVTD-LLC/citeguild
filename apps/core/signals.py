from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.analytics import USER_LOGGED_IN, has_analytics_consent, track_event
from apps.core.models import Profile, ProfileStates


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        profile = Profile.objects.create(user=instance)
        profile.track_state_change(
            to_state=ProfileStates.SIGNED_UP,
            source_function="create_user_profile signal",
        )

    if instance.id == 1:
        # Use update() to avoid triggering the signal again
        User.objects.filter(id=1).update(is_staff=True, is_superuser=True)


@receiver(user_logged_in, dispatch_uid="citeguild.track_user_logged_in")
def track_user_login(sender, request, user, **kwargs):
    profile = getattr(user, "profile", None)
    if profile is None or not has_analytics_consent(request):
        return

    backend = getattr(user, "backend", "") or ""
    current_state = (
        ProfileStates.SIGNED_UP if profile.state == ProfileStates.STRANGER else profile.state
    )
    track_event(
        profile,
        USER_LOGGED_IN,
        {"login_method": backend.split(".")[-1]},
        current_state=current_state,
        source_function="track_user_login signal",
    )
