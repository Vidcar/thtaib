# Spec Delta

## MODIFIED Requirements

### Requirement: API-042 - Use one control grammar across settings

Settings forms SHALL share appearance tokens and accessible control conventions. The compact Models surface SHALL use one label/native-value/reset row with help and provenance on demand rather than a standing provenance line. Other settings forms SHALL use one row grammar: the label, hover/focus help and a short provenance line (value, source and state, omitting unknown parts) on the left, the control on the right, and an optional hint underneath. Binary settings SHALL use a switch, two to five options a segmented choice, ordered numbers a slider with exact entry, long lists a select, and destructive confirmations a dialog. Default-following values SHALL appear as their resolved value in the control or a named default choice, with a reset action naming its verified target and exposing its known value on hover/focus; displaying the value MUST NOT create an override. Following a saved configuration and using the model's own default SHALL remain distinguishable when their resolver meanings differ. Unknown values SHALL remain explicit, and generic Inherited or Reset to inherited wording SHALL be replaced. Cards and controls SHALL take radius, padding, height and colour from the existing appearance tokens, so compact and comfortable densities and light and dark themes apply everywhere without a second appearance system.

#### Scenario: Edit an inherited model setting

- **WHEN** a person opens a model's settings, Defaults, or the chat model menu
- **THEN** each setting shows its effective value beside the control; Models exposes its source on demand, while shared settings forms retain provenance beside the control
- **AND** following or resetting to the named default clears only that layer's value while preserving the target's distinct resolver meaning.

#### Scenario: Narrow window and comfortable density

- **WHEN** the window is about 360 px wide or density is comfortable, in light or dark
- **THEN** rows stack the control under the label without horizontal scrolling
- **AND** section actions stay on one line.

#### Scenario: Compact Models and shared settings
- **WHEN** Models is opened and native controls are edited, then Chat, Agents or Settings is opened
- **THEN** Models uses its compact scoped layout while the shared consumers retain their own geometry, controls and appearance.
