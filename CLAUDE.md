# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

pelican-stat is a Pelican plugin and CLI (`pelican-stat`) that computes article statistics: site-wide word counts, a trend plot, and a `{% writing_stats %}` shortcode widget.

## Common commands

Tasks are [invoke](https://www.pyinvoke.org/) tasks defined in `tasks/` (collected in `tasks/__init__.py`) and run through `uv`. List them with `uv run inv --list`.

```bash
uv run inv env.init-dev               # uv sync with dev,test,style,security,git groups + install pre-commit hooks
uv run inv env.init-dev --no-pre-commit  # same, without installing hooks
uv run inv env.setup-pre-commit-hook  # install pre-commit, pre-push, commit-msg hooks
uv run inv test                       # pytest (default of test.run)
uv run inv test.cov                   # pytest --cov=pelican.plugins.stat tests/
uv run inv style.format               # ruff format on src, tests, tasks
uv run inv style                      # style.ruff (check --fix) + style.mypy + style.commit-check
uv run inv secure                     # pip-audit + bandit
uv run inv run-pre-commit-hooks       # pre-commit run --all-files --hook-stage pre-push
uv run inv git.commit                 # commit through commitizen (cz commit)
uv run inv build.dist                 # uv build
uv run inv doc.serve                  # mkdocs serve
uv run inv doc.build                  # mkdocs build --clean
```

Single test: `uv run pytest tests/test_wordcount.py::test_name`. Pytest config lives in `pyproject.toml` (`testpaths = "tests"`).

Pre-commit is the hook runner (not prek): `.pre-commit-config.yaml` runs `style.format` on commit, and `style`, `secure`, `test` on pre-push. Run it on specific files with `uv run pre-commit run --files <file>`. The `no-commit-to-branch` hook fails on `main`; CI runs with `SKIP=no-commit-to-branch,commitizen-branch`, and the same `SKIP=` prefix works locally.


Releases: pushes to `main` trigger `.github/workflows/main-updated.yaml`, which runs commitizen-action to bump the version and update `CHANGELOG.md` (skipped for `bump:` commits). A pushed tag triggers `.github/workflows/python-publish.yaml` (build, then PyPI publish). Don't hand-edit `CHANGELOG.md`.

## Architecture

Package: `src/pelican/plugins/stat/` (built with `uv_build`, module root `src`). The Pelican entry point is `register()` in `stat.py`, re-exported by `__init__.py`.

- `stat.py`: the plugin. `register()` connects four signals:
  1. `signals.initialized` -> `_initialize_shortcode`: stores settings and registers a Markdown preprocessor (`_ShortcodePreserver`) so the `{% writing_stats %}` shortcode survives Markdown conversion.
  2. `signals.all_generators_finalized` -> `_attach_word_count_stats`: accumulates articles across rounds (the primary build plus nested `i18n_subsites` builds), recomputes stats with `ArticleWordCountAggregator`, and puts them in each generator's context as `pelican_stat_word_count` and `pelican_stat_trend_plot_html`.
  3. `signals.content_written` -> `_substitute_shortcode_html`: replaces shortcode occurrences in rendered HTML with the widget markup.
  4. `signals.finalized` -> `_reset_word_count_cache`: resets the module-level accumulation state once the outermost `Pelican.run()` finishes.
  The long comment blocks at the top of `stat.py` explain why accumulation and substitution happen at these signals; read them before changing signal wiring.
- `wordcount.py`: `ArticleWordCountAggregator` computes the site-wide stats (CJK characters, English words, totals) from article HTML. It never reads Pelican settings; `stat.py` passes `include_block_code` in.
- `plotter.py`: `PelicanDataPlotter` builds the Plotly trend figure of posts over time (optional year filter and group-by-category).
- `collector.py`: `PelicanArticleDataCollector` builds a Pelican instance from a `pelicanconf.py` with `PLUGINS = []` and runs only the articles generator, for CLI use outside a normal build.
- `__main__.py`: click group `pelican-stat` with `collect`, `plot`, and `wordcount` commands (script entry in `pyproject.toml`).

Plugin settings (all optional, in `pelicanconf.py`): `PELICAN_STAT_SHORTCODE`, `PELICAN_STAT_LABELS`, `PELICAN_STAT_INCLUDE_CODE_BLOCKS`. They are documented in `docs/README.md`.

Tests are in `tests/` (one file per module plus `test_main.py` for the CLI); `tests/sample_pelican_project/` is a fixture site.

## Conventions

- **Conventional commits** via commitizen (`cz_conventional_commits`, `[tool.commitizen]` in `pyproject.toml`). The `commitizen` pre-commit hook checks messages; `style.commit-check` checks `origin/main..`.
- **Lint and types**: ruff (line length 110; extra rules `I`, `UP`, `PT`, `TID25`; every file needs `from __future__ import annotations`) and mypy over `src` and `tests`, with strict untyped-def settings for `pelican.plugins.stat.*`. `tasks` is linted by ruff as well. Bandit and pip-audit are the security checks.
- **Other pre-commit hooks**: codespell (extra words in `spelling_wordlist.txt`), markdownlint-cli2 (`.markdownlint.yaml`), blacken-docs, actionlint, and `no-commit-to-branch`.
- **Cruft template**: the repo derives from `Lee-W/cookiecutter-python-template` (recorded in `.cruft.json`). `.github/workflows/cruft-update.yaml` runs weekly and opens an accept PR (`cruft/update`) or a reject PR (`cruft/reject`). Template-owned files (`tasks/`, workflows, pre-commit config) may be overwritten by an update, so prefer small local changes to them.
- **Docs**: `docs/README.md` (also the package readme) and `docs/contributing.md`, built with mkdocs-material (`mkdocs.yml`) and deployed to `gh-pages` by `main-updated.yaml` via `inv doc.build`.
- **CI**: `python-check.yaml` runs `inv run-pre-commit-hooks` on pull requests.
