# Spec Delta

## ADDED Requirements

### Requirement: MOD-032 - Distinguish user-image and tool-image support

The active deployment's capability record SHALL distinguish accepted user images from image content returned by a tool. The model adapter SHALL preserve tool-call pairing, bounded image bytes and selected request settings when a supported tool image is sent to the endpoint. Failed, untested and inconclusive tool-image support MUST NOT be displayed as verified visual inspection. Other model uses SHALL remain available under their existing compatibility rules.

#### Scenario: Tool image reaches the model
- **WHEN** a vision deployment passes an actual tool-image probe and an authorized agent reads a screenshot
- **THEN** the outgoing endpoint request includes that image with the corresponding completed tool result and the response can refer to visible fixture details.

#### Scenario: User image alone has passed
- **WHEN** user-image input has passed but tool-image delivery has not
- **THEN** the product reports tool-image inspection as unverified while preserving ordinary text use.
