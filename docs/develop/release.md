# Release

A release is a tag `vX.Y.Z` that matches `version` in `pyproject.toml`; CI
builds and pushes the images.

1. On `main`, with a green pipeline: `uv version --bump patch` (or `minor`,
   `major`). Commit `pyproject.toml` and `uv.lock`.
2. `git tag -a v$(uv version --short) -m v$(uv version --short) && git push --follow-tags`
   (`--follow-tags` pushes annotated tags only).

   `scripts/release.sh patch|minor|major` does steps 1 and 2: it refuses
   unless on `main` with a clean tree, level with `origin/main` and the tag
   free, and asks before committing and pushing. It also does step 5.
3. The tag pipeline runs the tests and `migration-test` (an upgrade from the
   previous release), then `image-build`: it refuses a tag that differs from
   the version, builds both images, runs `scripts/smoke-test.sh` in the api
   image and pushes `$CI_REGISTRY_IMAGE:X.Y.Z`, `:latest`,
   `$CI_REGISTRY_IMAGE/frontend:X.Y.Z` and `/frontend:latest`.
4. Deploy: `INDEX_VERSION=X.Y.Z` in ediarum.deploy's `.env`, after
   `ediarum-index migrate --check` (README, "Update").
5. Publish to GitHub (`github.com/ediarum/ediarum.index`):
   `scripts/publish.sh X.Y.Z`. Then create the GitHub release from the
   tag by hand.

## The GitHub mirror

The public repository has no internal history. Each release is one snapshot
commit, "Release X.Y.Z" by TELOTA, on top of the previous one, tagged
`vX.Y.Z` there too. Its files are those of the internal tag `vX.Y.Z`, minus
`EXCLUDE` in `scripts/publish.sh` (`.gitlab-ci.yml`). Nothing is merged back.

`scripts/publish.sh` refuses a snapshot that contains internal hosts, repository
paths, home directories or token-like strings (`FORBIDDEN`, minus `ALLOWED`).
Fix the hit on `main`, or add it to `ALLOWED` if it is meant to be public.
`scripts/release.sh` runs this check (`publish.sh --check`) before it changes
anything, and publishes right after the GitLab push. If only the GitHub push
fails, rerun `scripts/publish.sh X.Y.Z`. `NO_GITHUB=1 scripts/release.sh …`
releases on GitLab only.

Set up once per clone:
`git remote add github git@github.com:ediarum/ediarum.index.git`.

Tags `v*` are protected (Settings → Repository → Protected tags): only
maintainers create releases, and the `docker-build` runner only runs for
protected refs.
