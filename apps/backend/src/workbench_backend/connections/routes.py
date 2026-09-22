"""Local-trust protected connection and write-only credential controls."""
from fastapi import APIRouter, Request
from workbench_backend.inference.schemas import DeletePreview
from workbench_backend.state.dependencies import dependency_preview_for_app
from workbench_backend.connections.schemas import ConnectionRecord, ConnectionUpdate, ConnectionWrite, CredentialWrite

router = APIRouter(prefix="/v1/connections")


@router.get("", response_model=list[ConnectionRecord])
def connections(request: Request):
    return request.app.state.connections.list()


@router.post("", response_model=ConnectionRecord)
def create(request: Request, body: ConnectionWrite):
    return request.app.state.connections.create(body)


@router.patch("/{connection_id}", response_model=ConnectionRecord)
def update(request: Request, connection_id: str, body: ConnectionUpdate):
    return request.app.state.connections.update(connection_id, body)


@router.delete("/{connection_id}", response_model=ConnectionRecord)
def disconnect(request: Request, connection_id: str):
    return request.app.state.connections.disconnect(connection_id)


@router.get("/{connection_id}/delete-preview", response_model=DeletePreview)
def connection_delete_preview(request: Request, connection_id: str):
    return dependency_preview_for_app(request.app.state, "connection", connection_id)


@router.get("/{connection_id}/credential/delete-preview", response_model=DeletePreview)
def credential_delete_preview(request: Request, connection_id: str):
    return dependency_preview_for_app(request.app.state, "credential", connection_id)


@router.post("/{connection_id}/test", response_model=ConnectionRecord)
async def test(request: Request, connection_id: str):
    return await request.app.state.connections.test(connection_id)


@router.put("/{connection_id}/credential", response_model=ConnectionRecord)
def credential(request: Request, connection_id: str, body: CredentialWrite):
    return request.app.state.connections.replace_credential(connection_id, body.secret.get_secret_value())


@router.delete("/{connection_id}/credential", response_model=ConnectionRecord)
def remove_credential(request: Request, connection_id: str):
    return request.app.state.connections.remove_credential(connection_id)
