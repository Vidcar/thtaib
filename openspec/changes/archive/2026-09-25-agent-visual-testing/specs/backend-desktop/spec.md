# Spec Delta

## ADDED Requirements

### Requirement: API-043 - Show visual testing access and evidence in Chat

The shared Chat setup SHALL show browser availability and Windows Off, Selected window and All windows controls with the resolved access and active session state. Window selection and broad access SHALL be explicit and revocable. Chat SHALL show a retained capture thumbnail and Open action with its page or window source and observation time, and Library SHALL expose the same authorized record. A text-only or unverified vision setup SHALL explain why pixel inspection is unavailable while keeping structural browser and accessibility inspection usable.

#### Scenario: Capture is inspectable
- **WHEN** an agent captures a permitted page or window
- **THEN** Chat shows the capture, its target and time, and the same retained item can be opened in Library without a second media store.

#### Scenario: Windows scope changes
- **WHEN** a person changes a conversation from All windows to Selected window
- **THEN** the shown effective access narrows immediately and subsequent calls cannot use the former broad grant.
