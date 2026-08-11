## User outcome

Describe the user problem, observable behavior, and why this scope belongs in the supported
Samsarix Orchestration product.

## Changes

- Describe the focused implementation changes.

## Compatibility, security, and operations

Describe workflow/schema/API compatibility, external effects, trust boundaries, privacy,
resource bounds, rollback, and any new dependency or network behavior. Write `None` only after
checking each area.

## Verification

- [ ] Ruff passes.
- [ ] Strict MyPy passes.
- [ ] Full branch-aware tests pass at or above the coverage floor.
- [ ] Bandit passes for shipped modules.
- [ ] Distribution build, metadata check, wheel-boundary check, and clean install pass when
      packaging changes.
- [ ] Documentation and changelog match the implemented behavior.
- [ ] No credentials, private data, generated artifacts, or unrelated changes are included.

## Deferred work

List deliberately deferred work, external requirements, and known limitations.
