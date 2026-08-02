from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SERVICES = {"db", "redis", "qdrant", "backend", "workers"}
PRIVATE_SERVICES = {"db", "redis", "qdrant", "workers"}


def _yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def test_production_compose_has_private_persistent_healthy_dependencies():
    compose = _yaml("docker-compose-prod.yml")
    services = compose["services"]

    assert REQUIRED_SERVICES <= services.keys()
    assert all("ports" not in services[name] for name in PRIVATE_SERVICES)
    assert services["db"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert services["redis"]["volumes"] == ["redis_data:/data"]
    assert services["qdrant"]["volumes"] == ["qdrant_data:/qdrant/storage"]
    assert all("healthcheck" in services[name] for name in ("db", "redis", "qdrant"))
    assert services["backend"]["healthcheck"]["test"][-1].find("/api/healthcheck") >= 0


def test_production_roles_share_one_required_immutable_image():
    services = _yaml("docker-compose-prod.yml")["services"]
    server_image = services["backend"]["image"]

    assert services["workers"]["image"] == server_image
    assert "APP_IMAGE:?" in server_image
    assert "latest" not in server_image
    assert services["backend"]["environment"]["APP_PROCESS_TYPE"] == "server"
    assert services["workers"]["environment"]["APP_PROCESS_TYPE"] == "worker"
    for role in ("backend", "workers"):
        assert services[role]["depends_on"] == {
            dependency: {"condition": "service_healthy"} for dependency in ("db", "redis", "qdrant")
        }


def test_deploy_workflow_publishes_and_deploys_only_the_git_sha_tag():
    workflow = _yaml(".github/workflows/deploy.yml")
    steps = workflow["jobs"]["build-and-deploy"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build and push")
    tags = build["with"]["tags"]
    deployments = [step for step in steps if step.get("uses") == "caprover/deploy-from-github@main"]

    assert tags == "${{ steps.image.outputs.image_name }}:${{ github.sha }}"
    assert deployments
    assert all(step["with"]["image"] == tags for step in deployments)
