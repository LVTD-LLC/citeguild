import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.core.choices import ProjectStates
from apps.core.models import Project, ProjectStateTransition
from apps.core.projects import ProjectHostConflict, ProjectService, normalize_sitemap_url


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])


def test_sitemap_url_normalization_is_deterministic():
    normalized, host = normalize_sitemap_url(" HTTPS://BÜCHER.Example.:443/sitemap.xml#part ")

    assert normalized == "https://xn--bcher-kva.example/sitemap.xml"
    assert host == "xn--bcher-kva.example"


def test_project_input_lengths_are_bounded_before_database_or_network():
    with pytest.raises(ValidationError, match="2048 characters"):
        normalize_sitemap_url(f"https://example.com/{'x' * 2048}")


@pytest.mark.django_db
def test_unsubscribed_profile_cannot_create_project(profile):
    with pytest.raises(PermissionDenied):
        ProjectService.create(
            owner=profile, name="Example", sitemap_url="https://example.com/sitemap.xml"
        )


@pytest.mark.django_db
def test_subscribed_profile_can_create_unlimited_distinct_projects(profile):
    subscribe(profile)

    first = ProjectService.create(
        owner=profile, name="First", sitemap_url="https://one.example/sitemap.xml"
    )
    second = ProjectService.create(
        owner=profile, name="Second", sitemap_url="https://two.example/sitemap.xml"
    )

    assert ProjectService.for_owner(profile).count() == 2
    assert {first.normalized_host, second.normalized_host} == {"one.example", "two.example"}


@pytest.mark.django_db
def test_project_queries_never_cross_owner_boundary(profile, django_user_model):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Private", sitemap_url="https://private.example/sitemap.xml"
    )
    other_user = django_user_model.objects.create_user(username="other", password="test")

    with pytest.raises(Project.DoesNotExist):
        ProjectService.get_for_owner(other_user.profile, project.uuid)


@pytest.mark.django_db
def test_normalized_host_is_unique_across_network(profile, django_user_model):
    subscribe(profile)
    ProjectService.create(
        owner=profile, name="Owner", sitemap_url="https://Example.com/sitemap.xml"
    )
    other_user = django_user_model.objects.create_user(username="other", password="test")
    subscribe(other_user.profile)

    with pytest.raises(ProjectHostConflict, match="operator resolution"):
        ProjectService.create(
            owner=other_user.profile,
            name="Duplicate",
            sitemap_url="https://example.com/another-sitemap.xml",
        )

    assert Project.objects.filter(normalized_host="example.com").count() == 1


@pytest.mark.django_db
def test_suspension_blocks_sync_and_preserves_transition_history(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Example", sitemap_url="https://example.com/sitemap.xml"
    )
    assert project.is_sync_eligible is True

    project = ProjectService.suspend(
        owner=profile, project_uuid=project.uuid, reason="operator_review"
    )

    assert project.state == ProjectStates.SUSPENDED
    assert project.is_sync_eligible is False
    assert project.suspended_at is not None
    transition = ProjectStateTransition.objects.get(project=project)
    assert transition.from_state == ProjectStates.ACTIVE
    assert transition.to_state == ProjectStates.SUSPENDED
    assert transition.reason == "operator_review"


@pytest.mark.django_db
def test_lost_subscription_makes_active_project_ineligible(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Example", sitemap_url="https://example.com/sitemap.xml"
    )
    profile.stripe_subscription_status = "canceled"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])

    assert project.is_sync_eligible is False


@pytest.mark.django_db
def test_project_service_update_changes_name_and_normalized_fields(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Before", sitemap_url="https://before.example/sitemap.xml"
    )

    project = ProjectService.update(
        owner=profile,
        project_uuid=project.uuid,
        name="After",
        sitemap_url="https://AFTER.example:443/news-sitemap.xml#ignored",
    )

    assert project.name == "After"
    assert project.normalized_host == "after.example"
    assert project.normalized_sitemap_url == "https://after.example/news-sitemap.xml"


@pytest.mark.django_db
def test_project_service_update_enforces_owner_name_and_host_constraints(
    profile, django_user_model
):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Owner", sitemap_url="https://owner.example/sitemap.xml"
    )
    ProjectService.create(
        owner=profile, name="Claimed", sitemap_url="https://claimed.example/sitemap.xml"
    )
    other_user = django_user_model.objects.create_user(username="other-update", password="test")
    subscribe(other_user.profile)

    with pytest.raises(Project.DoesNotExist):
        ProjectService.update(
            owner=other_user.profile,
            project_uuid=project.uuid,
            name="Takeover",
            sitemap_url="https://takeover.example/sitemap.xml",
        )
    with pytest.raises(ValidationError, match="name is required"):
        ProjectService.update(
            owner=profile,
            project_uuid=project.uuid,
            name="  ",
            sitemap_url=project.sitemap_url,
        )
    with pytest.raises(ProjectHostConflict, match="operator resolution"):
        ProjectService.update(
            owner=profile,
            project_uuid=project.uuid,
            name="Conflict",
            sitemap_url="https://CLAIMED.example/other.xml",
        )


@pytest.mark.django_db
def test_project_service_reactivate_clears_suspension_and_records_audit_transition(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Example", sitemap_url="https://example.com/sitemap.xml"
    )
    ProjectService.suspend(owner=profile, project_uuid=project.uuid, reason="operator_review")

    project = ProjectService.reactivate(owner=profile, project_uuid=project.uuid)

    assert project.state == ProjectStates.ACTIVE
    assert project.suspension_reason == ""
    assert project.suspended_at is None
    transitions = list(project.state_transitions.order_by("created_at"))
    assert [(item.from_state, item.to_state) for item in transitions] == [
        (ProjectStates.ACTIVE, ProjectStates.SUSPENDED),
        (ProjectStates.SUSPENDED, ProjectStates.ACTIVE),
    ]
