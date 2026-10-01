---
name: windows-execution
description: Run project builds, tests, scripts or command diagnosis correctly on Windows with explicit shell syntax, exit checks and owned process cleanup. Skip tasks that need no Windows command execution.
requires-project: true
required-tools: [execute]
---

Read the project manifests and observed environment before choosing executables or package managers. Execute uses cmd.exe on Windows; invoke PowerShell explicitly when its syntax is needed. Quote paths, including spaces, and use non-interactive commands.

Each execute call is a separate invocation. Inspect exit status and retained full output; a late failure must remain available beyond a preview. Never infer success from an empty output or an acknowledgement. Read references/commands.md when invoking PowerShell or diagnosing encoding.

Use selected start_preview for a preview server. Keep long work under an application-owned job lifecycle when available; stop it through its owner and confirm cleanup. Skill resources under /skills/ are virtual references; never pass those paths directly to a host interpreter. Shell commands have real host access and inherited environment; a project cwd is not a sandbox.
