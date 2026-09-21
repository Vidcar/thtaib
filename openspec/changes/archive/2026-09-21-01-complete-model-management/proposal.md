# Complete model installation, profiles and deployment lifecycle

## Why

The managed GGUF path must be usable from discovery through real generation, with recoverable downloads and truthful settings and ownership.

## What Changes

Complete discovery, installation jobs, repair, storage visibility, profile operations, on-demand loading, coordinated unload/delete/disconnect and first-use recovery.

## Capabilities

### Modified Capabilities

- `models`: Extend the existing bundle, profile, runtime, deployment and compatibility contracts.

## Impact

Work order **01 of 08**. Start here; inspect the existing implementation before changing it. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No diffusion/voice model installation, replacement downloader/supervisor, automatic CPU/model fallback or mandatory relocation feature.
