"""Authenticated Lab workbench API for Performance, Memory, and Challenges."""

from fastapi import APIRouter, Request

from workbench_backend.lab.workbench_schemas import ChallengeWrite, LabChallenge, LabLeaveRequest, LabRun, LabRunRequest

router = APIRouter(prefix="/v1/lab/workbench")


@router.get("/runs", response_model=list[LabRun])
def list_runs(request: Request):
    return request.app.state.lab_workbench.list_runs()


@router.post("/runs", response_model=LabRun)
def start_run(request: Request, body: LabRunRequest):
    return request.app.state.lab_workbench.start(body)


@router.get("/runs/{run_id}", response_model=LabRun)
def get_run(request: Request, run_id: str):
    return request.app.state.lab_workbench.get_run(run_id)


@router.post("/runs/{run_id}/stop", response_model=LabRun)
def stop_run(request: Request, run_id: str):
    return request.app.state.lab_workbench.stop(run_id)


@router.delete("/runs/{run_id}")
def delete_run(request: Request, run_id: str):
    request.app.state.lab_workbench.delete_run(run_id)
    return {"deleted": run_id}


@router.post("/leave")
def leave(request: Request, body: LabLeaveRequest):
    return request.app.state.lab_workbench.leave(body.run_ids)


@router.get("/challenges", response_model=list[LabChallenge])
def list_challenges(request: Request):
    return request.app.state.lab_workbench.list_challenges()


@router.post("/challenges", response_model=LabChallenge)
def add_challenge(request: Request, body: ChallengeWrite):
    return request.app.state.lab_workbench.save_challenge(body)


@router.put("/challenges/{challenge_id}", response_model=LabChallenge)
def edit_challenge(request: Request, challenge_id: str, body: ChallengeWrite):
    return request.app.state.lab_workbench.save_challenge(body, challenge_id)


@router.delete("/challenges/{challenge_id}")
def delete_challenge(request: Request, challenge_id: str):
    request.app.state.lab_workbench.delete_challenge(challenge_id)
    return {"deleted": challenge_id}
