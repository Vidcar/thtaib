"""WF-001: configuration links resolve setup and are not executable steps."""

from __future__ import annotations

import unittest

from workbench_backend.agents.definition_compiler import (
    ConfigurationAspect,
    DefinitionLink,
    DefinitionNode,
    LinkKind,
    MixedDefinition,
    NodeRole,
    TypedHandover,
    compile_definition,
)
from workbench_backend.errors import DefinitionCompileError


def mixed_definition() -> MixedDefinition:
    """Configuration + workflow definition used by the WF-001 acceptance check."""

    return MixedDefinition(
        id="mixed-review",
        nodes=[
            DefinitionNode(
                id="profile",
                role=NodeRole.configuration,
                label="model profile",
                model_profile_id="profile-local-qwen",
            ),
            DefinitionNode(
                id="tools",
                role=NodeRole.configuration,
                label="enabled tools",
                tools=["echo", "time_now"],
            ),
            DefinitionNode(
                id="skills",
                role=NodeRole.configuration,
                label="skills",
                skills=["skill-review"],
            ),
            DefinitionNode(
                id="memory",
                role=NodeRole.configuration,
                label="memory",
                memory=["mem-project-1"],
            ),
            DefinitionNode(
                id="environment",
                role=NodeRole.configuration,
                label="environment",
                environment="local-workspace",
            ),
            DefinitionNode(
                id="access",
                role=NodeRole.configuration,
                label="access",
                access="operator-confirm",
            ),
            DefinitionNode(
                id="policy",
                role=NodeRole.configuration,
                label="execution policy",
                execution_policy="no-silent-replay",
            ),
            DefinitionNode(id="draft", role=NodeRole.workflow_step, label="draft"),
            DefinitionNode(id="review", role=NodeRole.workflow_step, label="review"),
        ],
        links=[
            DefinitionLink(
                id="cfg-profile",
                source="profile",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.model_profile,
            ),
            DefinitionLink(
                id="cfg-tools",
                source="tools",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.tools,
            ),
            DefinitionLink(
                id="cfg-skills",
                source="skills",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.skills,
            ),
            DefinitionLink(
                id="cfg-memory",
                source="memory",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.memory,
            ),
            DefinitionLink(
                id="cfg-environment",
                source="environment",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.environment,
            ),
            DefinitionLink(
                id="cfg-access",
                source="access",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.access,
            ),
            DefinitionLink(
                id="cfg-policy",
                source="policy",
                target="draft",
                kind=LinkKind.configuration,
                aspect=ConfigurationAspect.execution_policy,
            ),
            DefinitionLink(
                id="wf-draft-review",
                source="draft",
                target="review",
                kind=LinkKind.workflow,
                handover=TypedHandover(kind="data", type_name="draft-text"),
            ),
        ],
    )


class DefinitionCompilerTests(unittest.TestCase):
    def test_mixed_definition_config_links_resolve_setup_not_steps(self) -> None:
        compiled = compile_definition(mixed_definition())

        self.assertEqual(compiled.definition_id, "mixed-review")
        self.assertEqual(compiled.setup.model_profile_id, "profile-local-qwen")
        self.assertEqual(compiled.setup.tools, ["echo", "time_now"])
        self.assertEqual(compiled.setup.skills, ["skill-review"])
        self.assertEqual(compiled.setup.memory, ["mem-project-1"])
        self.assertEqual(compiled.setup.environment, "local-workspace")
        self.assertEqual(compiled.setup.access, "operator-confirm")
        self.assertEqual(compiled.setup.execution_policy, "no-silent-replay")
        self.assertEqual(
            compiled.setup.resolved_from_link_ids,
            [
                "cfg-profile",
                "cfg-tools",
                "cfg-skills",
                "cfg-memory",
                "cfg-environment",
                "cfg-access",
                "cfg-policy",
            ],
        )
        self.assertEqual(compiled.step_ids, ["draft", "review"])
        self.assertEqual(compiled.executable_link_ids, ["wf-draft-review"])
        self.assertEqual(
            compiled.configuration_link_ids,
            [
                "cfg-profile",
                "cfg-tools",
                "cfg-skills",
                "cfg-memory",
                "cfg-environment",
                "cfg-access",
                "cfg-policy",
            ],
        )
        self.assertFalse(
            set(compiled.executable_link_ids) & set(compiled.configuration_link_ids)
        )
        self.assertNotIn("profile", compiled.step_ids)
        self.assertNotIn("cfg-profile", compiled.executable_link_ids)
        self.assertEqual(compiled.steps[0].outgoing_link_ids, ["wf-draft-review"])
        self.assertEqual(compiled.steps[1].incoming_link_ids, ["wf-draft-review"])
        self.assertEqual(compiled.steps[1].incoming_handovers[0].type_name, "draft-text")

    def test_treating_configuration_link_as_workflow_step_fails(self) -> None:
        definition = mixed_definition()
        links = list(definition.links)
        links[0] = DefinitionLink(
            id="cfg-profile",
            source="profile",
            target="draft",
            kind=LinkKind.workflow,
            handover=TypedHandover(kind="data", type_name="pretend-step"),
        )
        definition = definition.model_copy(update={"links": links})

        with self.assertRaises(DefinitionCompileError) as raised:
            compile_definition(definition)

        self.assertEqual(raised.exception.code, "config_link_as_step")
        self.assertIn("configuration", raised.exception.message.lower())
        self.assertIn("not executable", raised.exception.message.lower())


if __name__ == "__main__":
    unittest.main()
