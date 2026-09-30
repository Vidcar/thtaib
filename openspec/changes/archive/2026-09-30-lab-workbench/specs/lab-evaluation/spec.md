# Spec Delta

## REMOVED Requirements

### Requirement: LAB-001 - Separate engine measurements from task evaluation

**Reason**: Performance measurements now come from the loaded model's reported timings, and challenge checks live in their own specifications. This requirement still told Lab to use llama-bench.
**Migration**: Use `lab-speed` for prefill and generation measurements and `lab-challenges` for exact task checks. Do not add a second agent loop.

### Requirement: LAB-005 - Publish an extensible hardware-local trait catalogue

**Reason**: The catalogue mixed the new Performance, Memory, and Challenges screens with the older case-replay lab, including a single plain-sentence needle and unnamed tool cards.
**Migration**: Add Memory tests under `lab-memory` and challenges under `lab-challenges`. Vision in Lab and a plain-sentence needle are not part of this contract.

### Requirement: LAB-006 - Model Lab UX is trait runs, not case replay

**Reason**: The three-screen wording is replaced by the Lab destination and the Performance, Memory, and Challenges specifications. It also still described editable free-form sizes and a llama-bench chart.
**Migration**: Follow `lab`, `lab-speed`, `lab-memory`, and `lab-challenges`. Case capture remains specified by the requirements that this change does not remove.

### Requirement: LAB-008 - Measure engine traits honestly

**Reason**: Engine measurements are no longer defined as llama-bench runs. Reported prefill and generation timings from the loaded model replace that runner.
**Migration**: Follow `lab-speed`. A missing or failed measurement states the reason and does not invent a point.

### Requirement: LAB-014 - Hold the machine visibly while Lab runs

**Reason**: Lab no longer takes an exclusive hold on every loaded model. Single stream uses the saved loaded-model limit. Concurrent serving may load extra models only for that benchmark and then releases them.
**Migration**: Follow `lab-speed` for how a benchmark shares loaded models with the rest of the application.
