# Lab Memory

## Purpose

Specify the Memory view: exact needle tests that show whether a loaded model can recover a known code at several depths in its context.

## Requirements

### Requirement: MEM-001 - Choose one needle test and five depths

Memory SHALL run one needle test at a time. The person SHALL choose one of three tests: a single UUID needle, a multi-key needle, or a multi-value needle. Context size SHALL use the same legal choices as Performance and MUST NOT exceed the selected model's maximum. Five depths SHALL start on: the start, a quarter, halfway, three quarters, and near the end of the context. The person SHALL be able to turn a depth off. The deepest position MUST leave room for the question and a short answer, so the needle is not placed where that question would be cut off. A Memory run SHALL NOT create a Chat conversation.

#### Scenario: Depths start on

- **WHEN** a person opens Memory for a model with a selected context size
- **THEN** all five depths are on
- **AND** any depth can be turned off before the run starts

#### Scenario: The question still fits

- **WHEN** the near-the-end depth is run
- **THEN** the question and room for a short answer fit after the needle
- **AND** the run does not place the needle in that reserved tail

### Requirement: MEM-002 - Use three exact needle tasks

The single UUID test SHALL hide one UUID in ordinary filler, with no other codes. The multi-key test SHALL fill the context with other codes and ask for one of them. The multi-value test SHALL attach four UUID values to one name and ask for every value. The expected answer SHALL be known before the model is called. Scoring MUST look for that text in the model's answer and MUST NOT ask another model to judge it.

#### Scenario: Multi-key context is other codes

- **WHEN** the person runs the multi-key needle
- **THEN** the context is filled with other codes
- **AND** the expected answer is the one requested code

#### Scenario: Multi-value requires every code

- **WHEN** the person runs the multi-value needle
- **THEN** the expected answer is all four UUID values
- **AND** an answer that omits any value does not pass

### Requirement: MEM-003 - Show each depth as it finishes

Each finished depth SHALL appear immediately as found or missed, with the depth and the text the model returned. A missed multi-value depth SHALL show which of the four values were absent. Memory MUST NOT present a single blended percentage as the only result. Stop SHALL keep finished depths and skip depths that have not started.

#### Scenario: A depth appears before the run finishes

- **WHEN** the first depth finishes and later depths are still running
- **THEN** that depth shows found or missed and the model's text
- **AND** later depths are not marked found or missed yet

#### Scenario: Stop keeps finished depths

- **WHEN** the person stops after two depths have finished
- **THEN** those two rows remain
- **AND** the depths that had not started have no result
