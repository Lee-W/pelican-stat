[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg?style=flat-square)](https://conventionalcommits.org)
[![GitHub Actions](https://github.com/Lee-W/pelican-stat/actions/workflows/python-check.yaml/badge.svg)](https://github.com/Lee-W/pelican-stat/actions/workflows/python-check.yaml)
[![PyPI Package latest release](https://img.shields.io/pypi/v/pelican_stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![PyPI Package download count (per month)](https://img.shields.io/pypi/dm/pelican_stat?style=flat-square)](https://pypi.org/project/pelican_stat/)
[![Supported versions](https://img.shields.io/pypi/pyversions/pelican-stat.svg?style=flat-square)](https://pypi.org/project/pelican_stat/)

# pelican_stat

Generate Pelican article statistics from the command line or expose them to
Pelican themes and content through a plugin.

## Getting Started

### Prerequisites

* [uv tool]

[uv tool]: https://docs.astral.sh/uv/concepts/tools/

## Pelican plugin

Install `pelican_stat` in the same environment as your Pelican site:

```sh
uv add pelican_stat
```

Then enable the plugin in `pelicanconf.py`:

```python
PLUGINS = [
    "pelican.plugins.stat",
]
```

The plugin adds these values to the template context:

* `pelican_stat_word_count`: a mapping containing `post_count`,
  `cjk_char_count`, `english_word_count`, `total_char_count`,
  `writing_years`, `average_chars_per_article`, and
  `median_chars_per_article`.
* `pelican_stat_trend_plot_html`: a Plotly HTML fragment. Render it with the
  Jinja `safe` filter and make sure the theme loads Plotly.js.

For example:

```jinja2
{{ pelican_stat_word_count.total_char_count }}
{{ pelican_stat_trend_plot_html | safe }}
```

### Writing statistics shortcode

In Markdown content, put the full widget on its own line:

```text
{% writing_stats %}
```

The full widget shows CJK characters, English words, total characters,
average characters per post, and median characters per post. A compact
variant shows only total and average characters:

```text
{% writing_stats compact %}
```

The widget includes scoped styles and chooses its labels from the content's
`Lang` metadata, then `DEFAULT_LANG`, and finally English. English (`en`) and
Taiwanese Mandarin (`zh-TW`) labels are built in; language matching is
case-insensitive. Other language tags, including bare `zh`, fall back to
English.

### Plugin settings

All settings are optional and belong in `pelicanconf.py`:

| Setting | Default | Description |
| --- | --- | --- |
| `PELICAN_STAT_SHORTCODE` | `"writing_stats"` | Changes the shortcode name. For example, `"blog_stats"` enables `{% blog_stats %}` and `{% blog_stats compact %}`. |
| `PELICAN_STAT_LABELS` | `{}` | Partially overrides the built-in labels. Use a mapping keyed by `en` or `zh-TW`, with statistic field names as the nested keys. |
| `PELICAN_STAT_INCLUDE_CODE_BLOCKS` | `False` | Includes text inside block-level `<pre>` elements in word and character statistics. Inline `<code>` text is always included. |

Label overrides are merged with the selected built-in locale, so unspecified
labels keep their defaults:

```python
PELICAN_STAT_LABELS = {
    "en": {
        "total_char_count": "Characters Written",
    },
    "zh-TW": {
        "total_char_count": "累積字元數",
        "average_chars_per_article": "平均每篇字元數",
    },
}
```

The available label keys are the seven keys listed under
`pelican_stat_word_count` above.

## Command-line usage

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

or

```sh
pelican-stat wordcount --help
```

## Contributing

See [Contributing](contributing.md)

## Authors

Wei Lee <weilee.rx@gmail.com>

Created from [Lee-W/cookiecutter-python-template] version 3.0.0

[Lee-W/cookiecutter-python-template]: https://github.com/Lee-W/cookiecutter-python-template/tree/3.0.0
