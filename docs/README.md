[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg?style=flat-square)](https://conventionalcommits.org)
[![GitHub Actions](https://github.com/Lee-W/pelican-stat/actions/workflows/python-check.yaml/badge.svg)](https://github.com/Lee-W/pelican-stat/actions/workflows/python-check.yaml)
[![PyPI Package latest release](https://img.shields.io/pypi/v/pelican_stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![PyPI Package download count (per month)](https://img.shields.io/pypi/dm/pelican_stat?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![Supported versions](https://img.shields.io/pypi/pyversions/pelican-stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)

# pelican_stat

CLI tool for generating pelican article statistics

## Getting Started

### Prerequisites

* [uv tool]

[uv tool]: https://docs.astral.sh/uv/concepts/tools/

## Usage

For installing this tool, I suggest using [uv tool], pipx or something similar.

```sh
uv tool install pelican_stat
```

After installation, you can see the detail by add `--help` flag.

e.g.,

```sh
pelican-stat --help
```

or

```sh
pelican-stat collect --help
```

or

```sh
pelican-stat plot --help
```

## Contributing

See [Contributing](contributing.md)

## Authors

Wei Lee <weilee.rx@gmail.com>

Created from [Lee-W/cookiecutter-python-template] version 3.0.0

[Lee-W/cookiecutter-python-template]: https://github.com/Lee-W/cookiecutter-python-template/tree/3.0.0
