[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![pypi-stat](https://img.shields.io/pypi/v/pelican-stat)](https://img.shields.io/pypi/v/pelican-stat)

# pelican_stat

cli tool for generating pelican article statistics

## Getting Started

### Prerequisites
* [pipx](https://github.com/pipxproject/pipx)

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

Created from [Lee-W/cookiecutter-python-template](https://github.com/Lee-W/cookiecutter-python-template/) version 0.6.1
