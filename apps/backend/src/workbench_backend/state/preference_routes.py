from fastapi import APIRouter, Request

from workbench_backend.state.preferences import PermissionGrant, PresentationPreferences, ProjectFileGrantRequest

router = APIRouter(prefix="/v1/settings")


@router.get("/presentation")
def preferences(request: Request) -> PresentationPreferences:
    return request.app.state.preferences.preferences()


@router.put("/presentation")
def save_preferences(request: Request, body: PresentationPreferences) -> PresentationPreferences:
    return request.app.state.preferences.save_preferences(body)


@router.patch("/presentation")
def update_preferences(request: Request, body: PresentationPreferences) -> PresentationPreferences:
    return request.app.state.preferences.update_preferences(body)


@router.get("/grants")
def grants(request: Request) -> list[PermissionGrant]:
    return request.app.state.preferences.grants()


@router.post("/grants/project-files", response_model=PermissionGrant)
def allow_project_files(request: Request, body: ProjectFileGrantRequest) -> PermissionGrant:
    project = request.app.state.setups.get_project(body.project_id, require_active=True)
    if project.missing:
        from workbench_backend.errors import HarnessError
        raise HarnessError("This project folder is missing.", code="project_missing", status_code=409)
    return request.app.state.preferences.allow_project_files(project, body)


@router.delete("/grants/{grant_id}")
def revoke(request: Request, grant_id: str) -> dict[str, bool]:
    request.app.state.preferences.revoke(grant_id)
    return {"revoked": True}
