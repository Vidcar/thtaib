# Spec Delta

## ADDED Requirements

### Requirement: AGT-023 - Read visual evidence through the existing agent loop

The shared Chat harness SHALL use native `read_file` for authorized project images and retained captures, including in a project-free conversation that has capture access. A supported image read SHALL reach the selected vision deployment as image content paired with its tool result; text-only or unverified visual support SHALL produce an actionable capability result rather than a fabricated visual description. Capture and browser/window tools SHALL remain subject to the frozen run setup, Work mode, helper authority intersection, tool budgets and cancellation rules.

#### Scenario: Visual capture in project-free Chat
- **WHEN** a browser screenshot is retained during a project-free conversation and its agent reads the capture path
- **THEN** the image is delivered to a verified vision model without granting project file or shell access.

#### Scenario: Helper cannot widen visual access
- **WHEN** a named helper attempts a browser or window tool outside its parent conversation's selected access
- **THEN** dispatch refuses it before the worker acts.
