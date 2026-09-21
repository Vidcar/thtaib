# lab-evaluation delta

## ADDED Requirements

### Requirement: LAB-013 - Measure real concurrent sessions and child load under Lab ownership

Lab SHALL execute the saved independent-session and child-load tests through verified shared admission using the same versioned tasks/configuration as the serial baseline. These are controlled Lab-owned concurrent workloads under the exclusive reservation. Record correctness, failures, queue time, responsiveness, total task duration, throughput and available memory separately. More simultaneous work is not declared faster without measurement; missing telemetry remains unavailable.

#### Scenario: Serial versus concurrent

- **WHEN** the saved session/child workload runs serially and concurrently
- **THEN** comparable actual results expose both performance and correctness under Lab ownership, without claiming uncontrolled external clients are reserved.
