# Releasing BrainGraph

The project name `braingraph` is already registered on PyPI. PyPI currently lists `0.1.1`; this source tree prepares `0.2.0` as the next release. Building these files does not publish them.

## Before release

1. Confirm the PyPI project owner authorizes the V2 release and the maintainers/author metadata are correct.
2. Review `CHANGELOG.md` and replace the `0.2.0 - Unreleased` heading with the release date.
3. Push this complete V2 source tree to `https://github.com/Dislike12/BrainGraph-V2`. Keep the V1 repository `https://github.com/Dislike12/BrainGraph` unchanged.
4. Confirm the repository shown in `[project.urls]` matches the V2 repository and contains this source and release workflow.
5. Run the quality and packaging checks from the project root:

   ```shell
   python -m pip install -e ".[dev]"
   python -m pytest -q
   python -m ruff check .
   python -m build
   python -m twine check dist/*
   ```

6. Inspect the wheel and source distribution contents. Ensure no `.env`, credentials, `.braingraph/`, test output, or unrelated internship documents are included.
7. Tag the reviewed source as `v0.2.0` and create a GitHub Release for that tag.

## Configure PyPI trusted publishing

Before publishing the first GitHub release, an owner of the existing PyPI project must configure a trusted publisher for:

- PyPI project: `braingraph`
- GitHub owner: `Dislike12`
- GitHub repository: `BrainGraph-V2`
- Workflow filename: `.github/workflows/publish.yml`
- GitHub environment: `pypi`

The workflow runs tests, lint, builds and checks both distributions, then requests a short-lived OIDC publishing identity from PyPI. It runs only when a GitHub Release is published. No PyPI API token is stored in the source tree. The publisher configuration must be set up by an account authorized for the existing PyPI project.

### First publish troubleshooting

The first `v0.2.0` GitHub Release run completed build, tests, lint, and `twine check` successfully, but PyPI rejected OIDC with `invalid-publisher` / `no corresponding publisher`. The GitHub OIDC claims were:

- subject: `repo:Dislike12/BrainGraph-V2:environment:pypi`
- workflow: `Dislike12/BrainGraph-V2/.github/workflows/publish.yml`
- environment: `pypi`
- tag ref: `refs/tags/v0.2.0`

The PyPI project owner must register a trusted publisher matching those repository, workflow, and environment values. After it is configured, rerun the failed `Publish to PyPI` GitHub Actions run or republish the existing GitHub Release. Do not create a different package name or version just to work around a missing publisher configuration.

## Manual alternative

If trusted publishing cannot be configured, an authorized owner may build locally and use `python -m twine upload dist/*`. Twine will prompt for credentials; enter them directly in the terminal and never paste them into source, chat, or committed workflow files. Do not upload until the exact wheel and sdist have passed `twine check` and have been reviewed.

## After publishing

- Verify `https://pypi.org/project/braingraph/0.2.0/` shows the expected metadata and README.
- In a clean Python 3.12 environment, run `python -m pip install braingraph==0.2.0`, `braingraph --version`, and `braingraph scan <small-test-project> --no-open`.
- Confirm the scan creates `<small-test-project>/.braingraph/` and prints the dashboard URL.
- Keep `0.1.1` available as the prior release; do not replace or delete it.