import type {
  SchemaLocalSessionTrustContract,
  SchemaRunLifecycleContract,
  SchemaRunLifecycleStatus,
} from "../generated/shared-contracts/openapi";

/** Generated shared-contract consumer aliases. Do not hand-edit generated sources. */
export type LocalSessionTrustContract = SchemaLocalSessionTrustContract;
export type RunLifecycleContract = SchemaRunLifecycleContract;
export type RunLifecycleStatus = SchemaRunLifecycleStatus;

export function isRunLifecycleLive(status: RunLifecycleStatus): boolean {
  switch (status) {
    case "queued":
    case "running":
    case "cancel_requested":
      return true;
    case "cancelled":
    case "completed":
    case "failed":
      return false;
    default: {
      const exhaustive: never = status;
      return exhaustive;
    }
  }
}
