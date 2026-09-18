## Summary

Describe the problem and the change. Clearly identify anything that remains mock/demo-only or
planned.

## Validation

- [ ] Relevant backend tests pass.
- [ ] Ruff passes.
- [ ] Frontend lint passes.
- [ ] Frontend production build passes.
- [ ] Relevant dependency audits pass.
- [ ] `git diff --check` passes.

## Review checklist

- [ ] The change is focused and unrelated work is excluded.
- [ ] Security and customer-data implications were considered.
- [ ] No secrets, credentials, sensitive logs or generated build output are included.
- [ ] New backend behavior has tests.
- [ ] Database changes use a new Alembic migration; historical migrations are unchanged.
- [ ] Documentation and configuration examples are updated where needed.
- [ ] Implemented, mock/demo and planned behavior are described accurately.

## Notes for reviewers

List compatibility decisions, migrations, manual checks or follow-up work.
