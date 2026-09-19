from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Project, ProjectDeletionCleanup
from apps.core.projects import ProjectService
from apps.core.tests.test_sitemap_details import subscribe
from apps.search.cleanup import recover_project_deletions
from apps.search.qdrant import delete_project_points


@pytest.mark.django_db(transaction=True)
def test_deletion_commits_and_retains_cleanup_when_broker_is_down(auth_client, profile, settings):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Delete me", sitemap_url="https://delete.example/sitemap.xml"
    )
    settings.CITEGUILD_INDEXING_ENABLED = True

    with patch("apps.search.qdrant.async_task", side_effect=ConnectionError("broker unavailable")):
        response = auth_client.post(
            reverse("delete_sitemap", args=[project.uuid]), {"confirmation": project.name}
        )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert not Project.objects.filter(pk=project.pk).exists()
    assert ProjectDeletionCleanup.objects.filter(project_uuid=project.uuid).exists()


@pytest.mark.django_db
def test_cleanup_intent_rolls_back_with_deletion(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile, name="Keep me", sitemap_url="https://keep.example/sitemap.xml"
    )
    with patch("apps.search.qdrant.queue_project_deletion") as queue_cleanup:
        with pytest.raises(RuntimeError), transaction.atomic():
            ProjectService.delete(owner=profile, project_uuid=project.uuid)
            raise RuntimeError("rollback")

    assert Project.objects.filter(pk=project.pk).exists()
    assert not ProjectDeletionCleanup.objects.exists()
    queue_cleanup.assert_not_called()


@pytest.mark.django_db
def test_failed_vector_cleanup_is_retained_and_retried(settings):
    settings.CITEGUILD_INDEXING_ENABLED = True
    project_uuid = uuid4()
    ProjectDeletionCleanup.objects.create(project_uuid=project_uuid)

    with patch("apps.search.qdrant.get_qdrant_client") as get_client:
        client = get_client.return_value
        client.collection_exists.return_value = True
        client.delete.side_effect = TimeoutError
        assert recover_project_deletions() == 0
        pending = ProjectDeletionCleanup.objects.get(project_uuid=project_uuid)
        assert pending.next_attempt_at > timezone.now()
        assert recover_project_deletions() == 0
        assert client.delete.call_count == 1

        ProjectDeletionCleanup.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        client.delete.side_effect = None
        assert recover_project_deletions() == 1
        assert not ProjectDeletionCleanup.objects.exists()
        assert client.delete.call_args.kwargs["wait"] is True
        # Delivery can be duplicated after worker/broker recovery.
        assert delete_project_points(str(project_uuid)) == str(project_uuid)


@pytest.mark.django_db
def test_cleanup_is_bounded_and_pauses_when_indexing_is_disabled(settings):
    ProjectDeletionCleanup.objects.bulk_create(
        [ProjectDeletionCleanup(project_uuid=uuid4()) for _ in range(101)]
    )
    with patch("apps.search.cleanup.delete_project_points", side_effect=TimeoutError) as cleanup:
        settings.CITEGUILD_INDEXING_ENABLED = False
        assert recover_project_deletions() == 0
        cleanup.assert_not_called()
        settings.CITEGUILD_INDEXING_ENABLED = True
        assert recover_project_deletions() == 0
        assert cleanup.call_count == 100
        assert ProjectDeletionCleanup.objects.count() == 101


@pytest.mark.django_db
def test_absent_collection_completes_cleanup():
    project_uuid = uuid4()
    ProjectDeletionCleanup.objects.create(project_uuid=project_uuid)
    with patch("apps.search.qdrant.get_qdrant_client") as get_client:
        get_client.return_value.collection_exists.return_value = False
        delete_project_points(str(project_uuid))
        get_client.return_value.delete.assert_not_called()
    assert not ProjectDeletionCleanup.objects.exists()
