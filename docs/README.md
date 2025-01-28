[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg?style=flat-square)](https://conventionalcommits.org)
[![Github Actions](https://github.com/Lee-W/pelican_stat/actions/workflows/python-check.yaml/badge.svg)](https://github.com/Lee-W/pelican_stat/actions/workflows/python-check.yaml)

[![PyPI Package latest release](https://img.shields.io/pypi/v/pelican_stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![PyPI Package download count (per month)](https://img.shields.io/pypi/dm/pelican_stat?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![Supported versions](https://img.shields.io/pypi/pyversions/pelican_stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)

# pelican_stat

CLI tool for generating pelican article statistics

## Getting Started

### Prerequisites

* [Python](https://www.python.org/downloads/)

## Usage

As I pin pelican to 4.5.4 for API consistency, I suggest using pipx (or any other virtual environment mechanism) to install this tool.

```sh
pipx install pelican_stat
```

After installation, you can see the detail by add `--help` flag.

e.g.,

```sh
pelican-stat --help
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
