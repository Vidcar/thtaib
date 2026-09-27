## MODIFIED Requirements

### Requirement: MOD-032 - Distinguish user-image and tool-image support

The active deployment's capability record SHALL distinguish accepted user images from image content returned by a tool. The model adapter SHALL preserve tool-call pairing, bounded image bytes and selected request settings when a supported tool image is sent to the endpoint. Failed, untested and inconclusive tool-image support MUST NOT be displayed as verified visual inspection. An untested tool-image check MAY run once when a screenshot is taken on a vision setup. Until it passes, the product SHALL NOT send the image and SHALL keep the page text available. Other model uses SHALL remain available under their existing compatibility rules.

Automatic capability checks SHALL retain their outcomes as setup evidence without publishing their reasoning, answers or synthetic tool calls into the conversation display or execution history. When the active setup passes the required checks, the same screenshot's next model request SHALL use the newly verified image capabilities before unsupported-content filtering. The product MUST NOT substitute test images for the retained screenshot or change the selected model, request settings or context capacity to enable image delivery.

#### Scenario: Tool image reaches the model
- **WHEN** a vision deployment passes an actual tool-image probe and an authorized agent reads a screenshot
- **THEN** the outgoing endpoint request includes that image with the corresponding completed tool result and the response can refer to visible fixture details.

#### Scenario: User image alone has passed
- **WHEN** user-image input has passed but tool-image delivery has not
- **THEN** the product reports tool-image inspection as unverified while preserving ordinary text use.

#### Scenario: First screenshot verifies support
- **WHEN** an active vision setup has untested image capabilities and its automatic checks pass during screenshot handling
- **THEN** the next model request includes the actual retained screenshot and preserves the tool result, selected setup and context capacity
- **AND** the conversation contains no capability-test reasoning, colour replies or synthetic tool activity.

#### Scenario: Screenshot check cannot verify support
- **WHEN** either required image capability is failed or inconclusive
- **THEN** the image remains withheld and the page text remains available without presenting visual inspection as verified
- **AND** internal test output remains absent from the conversation.
