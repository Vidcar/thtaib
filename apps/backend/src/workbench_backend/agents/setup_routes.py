"""Shared project and reusable-agent configuration API."""

from fastapi import APIRouter, Request
from workbench_backend.agents.setup_service import cleared_configuration_fields
from workbench_backend.inference.schemas import DeletePreview
from workbench_backend.state.dependencies import dependency_preview_for_app

from workbench_backend.agents.setup_schemas import (
    AgentSetupCreateRequest, AgentSetupDuplicateRequest, AgentSetupUpdateRequest,
    AgentSetupVersion, AgentSetupView, ProjectCreateRequest, ProjectFiles,
    ProjectRecord, ProjectUpdateRequest, ResolvedSetupSelection, SetupConfiguration,
    SetupResolutionRequest,
)

router = APIRouter(prefix="/v1")


@router.get("/projects", response_model=list[ProjectRecord])
def projects(request: Request, include_inactive: bool = False):
    return request.app.state.setups.list_projects(include_inactive=include_inactive)


@router.post("/projects", response_model=ProjectRecord)
def create_project(request: Request, body: ProjectCreateRequest):
    return request.app.state.setups.create_project(body)


@router.get("/projects/{project_id}", response_model=ProjectRecord)
def project(request: Request, project_id: str):
    return request.app.state.setups.get_project(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRecord)
def update_project(request: Request, project_id: str, body: ProjectUpdateRequest):
    return request.app.state.setups.update_project(project_id, body)


@router.delete("/projects/{project_id}", response_model=ProjectRecord)
def remove_project(request: Request, project_id: str):
    return request.app.state.setups.remove_project(project_id)


@router.get("/projects/{project_id}/delete-preview", response_model=DeletePreview)
def project_delete_preview(request: Request, project_id: str):
    return dependency_preview_for_app(request.app.state, "project", project_id)


@router.get("/projects/{project_id}/files", response_model=ProjectFiles)
def project_files(request: Request, project_id: str, path: str = ""):
    return request.app.state.setups.project_files(project_id, path)


@router.get("/agent-setups", response_model=list[AgentSetupView])
def agent_setups(request: Request, include_inactive: bool = False):
    return request.app.state.setups.list_setups(include_inactive=include_inactive)


@router.post("/agent-setups", response_model=AgentSetupView)
def create_setup(request: Request, body: AgentSetupCreateRequest):
    return request.app.state.setups.create_setup(body)


@router.get("/agent-setups/{setup_id}", response_model=AgentSetupView)
def agent_setup(request: Request, setup_id: str):
    return request.app.state.setups.get_setup(setup_id)


@router.patch("/agent-setups/{setup_id}", response_model=AgentSetupView)
def update_setup(request: Request, setup_id: str, body: AgentSetupUpdateRequest):
    return request.app.state.setups.update_setup(setup_id, body)


@router.delete("/agent-setups/{setup_id}", response_model=AgentSetupView)
def remove_setup(request: Request, setup_id: str):
    return request.app.state.setups.remove_setup(setup_id)


@router.get("/agent-setups/{setup_id}/delete-preview", response_model=DeletePreview)
def setup_delete_preview(request: Request, setup_id: str):
    return dependency_preview_for_app(request.app.state, "agent_setup", setup_id)


@router.get("/agent-setups/{setup_id}/versions", response_model=list[AgentSetupVersion])
def setup_versions(request: Request, setup_id: str):
    request.app.state.setups.get_setup(setup_id)
    return request.app.state.app_store.list_agent_setup_versions(setup_id)


@router.post("/agent-setups/{setup_id}/duplicate", response_model=AgentSetupView)
def duplicate_setup(request: Request, setup_id: str, body: AgentSetupDuplicateRequest):
    return request.app.state.setups.duplicate_setup(setup_id, body.name)


@router.get("/setup-defaults", response_model=SetupConfiguration)
def setup_defaults(request: Request):
    return request.app.state.app_store.get_setup_defaults()


@router.put("/setup-defaults", response_model=SetupConfiguration)
def save_setup_defaults(request: Request, body: SetupConfiguration):
    return request.app.state.app_store.put_setup_defaults(body)


@router.post("/setup-resolution", response_model=ResolvedSetupSelection)
def resolve_setup(request: Request, body: SetupResolutionRequest):
    return request.app.state.setups.resolve(**body.model_dump(exclude={"overrides"}), overrides=body.overrides, override_cleared_fields=cleared_configuration_fields(body.overrides))
