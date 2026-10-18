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
    qdrant_health = services["qdrant"]["healthcheck"]["test"][-1]
    assert "/proc/net/tcp" in qdrant_health
    assert "/dev/tcp" not in qdrant_health
    backend_health = services["backend"]["healthcheck"]["test"][-1]
    assert "/api/healthcheck" in backend_health
    assert "response.status == 200" in backend_health


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


def test_deploy_workflow_publishes_and_deploys_one_attempt_specific_image():
    workflow = _yaml(".github/workflows/deploy.yml")
    steps = workflow["jobs"]["build-and-deploy"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build and push")
    install = next(step for step in steps if step.get("name") == "Install CapRover CLI")
    tags = build["with"]["tags"]
    deployments = [
        step
        for step in steps
        if step.get("name") in {"Deploy server to CapRover", "Deploy workers to CapRover"}
    ]

    image_tag = "${{ github.sha }}-${{ env.EXPECTED_DEPLOYMENT }}"
    assert tags == "${{ steps.image.outputs.image_name }}:" + image_tag
    assert build["with"]["build-args"].splitlines() == [
        "CITEGUILD_RELEASE=${{ github.sha }}",
        "CITEGUILD_DEPLOYMENT_ID=${{ env.EXPECTED_DEPLOYMENT }}",
    ]
    assert install["run"] == "npm install --global caprover@2.3.1"
    assert len(deployments) == 2
    assert all(
        step["env"]["IMAGE_NAME"] == "${{ steps.image.outputs.image_name }}" for step in deployments
    )
    assert all("caprover deploy" in step["run"] for step in deployments)
    assert all(step["env"]["IMAGE_TAG"] == image_tag for step in deployments)
    assert all('--imageName "${IMAGE_NAME}:${IMAGE_TAG}"' in step["run"] for step in deployments)


def test_deploy_workflow_gates_workers_on_aggregate_production_health():
    workflow = _yaml(".github/workflows/deploy.yml")
    job = workflow["jobs"]["build-and-deploy"]
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    health = next(step for step in steps if step.get("name") == "Verify production health")
    worker_health = next(
        step for step in steps if step.get("name") == "Verify web and worker deployment readiness"
    )

    assert workflow["env"]["PRODUCTION_HEALTHCHECK_URL"] == "${{ vars.PRODUCTION_HEALTHCHECK_URL }}"
    assert names.index("Deploy server to CapRover") < names.index("Verify production health")
    assert names.index("Verify production health") < names.index("Deploy workers to CapRover")
    assert names.index("Deploy workers to CapRover") < names.index(worker_health["name"])
    assert workflow["concurrency"] == {"group": "citeguild-production", "cancel-in-progress": False}
    assert job["env"]["EXPECTED_RELEASE"] == "${{ github.sha }}"
    assert job["env"]["EXPECTED_DEPLOYMENT"] == "${{ github.run_id }}-${{ github.run_attempt }}"
    assert health["run"] == "python3 deployment/wait_ready.py"
    assert worker_health["run"] == "python3 deployment/wait_ready.py --worker"
