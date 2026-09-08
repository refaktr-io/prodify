# Contributing

Thanks for helping. A few things that make contributions easy to review:

## Before you start

- Open an issue first for anything beyond a small fix, especially changes to the generated CloudFormation template — those ship to other people's AWS accounts.
- Read `CLAUDE.md`: it's written for coding agents, but it's also the shortest accurate description of how the pieces fit together.

## Development

There's no build step for the Python code. Validate and test with:

```bash
cfn-lint backend/infrastructure/template.yaml
python -m pytest
```

To deploy your own instance for end-to-end testing, follow "Deploy your own instance" in the README. Please don't test against the hosted Prodify API with anything other than throwaway projects.

## Pull requests

- Keep template changes and Lambda changes in separate PRs where possible.
- If you change `backend/docker/content-deployer/`, note the new image digest in the PR description; maintainers push the image and update the template mapping.
- Tests for new behavior go in `tests/`; fixtures for new project shapes go in `tests/fixtures/` and must be synthetic (no real exported projects, no credentials).

By contributing you agree that your contributions are licensed under the Apache License 2.0.
