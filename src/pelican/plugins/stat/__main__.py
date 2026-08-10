from __future__ import annotations

import json
import os
import sys

import click

from .collector import PelicanArticleDataCollector
from .plotter import PelicanDataPlotter
from .wordcount import ArticleWordCountAggregator


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument(
    "pelican_conf_path",
    required=True,
    default="pelicanconf.py",
)
@click.argument(
    "output_path",
    required=True,
    default="article_metadata.json",
)
def collect(pelican_conf_path: str, output_path: str) -> None:
    """Collect data from pelican project and export article metadata"""
    if not os.path.exists(pelican_conf_path):
        print(f"Configuration file {pelican_conf_path} does not exists", file=sys.stderr)
        sys.exit(1)

    data_collector = PelicanArticleDataCollector(pelican_conf_path)
    data_collector.export(output_path)


@main.command()
@click.option(
    "--pelican-conf-path",
    help=(
        "path to pelican site configuration file (e.g., pelicanconf.py). "
        "note that either --pelican-conf-path or --articles-metadata-path "
        "needs to be provided"
    ),
)
@click.option(
    "--articles-metadata-path",
    help=(
        "path to collected articles metadata. "
        "note that either --pelican-conf-path or --articles-metadata-path "
        "needs to be provided"
    ),
)
@click.option(
    "--output-path",
    required=True,
    default="trend_plot.html",
    help="path for the output plot",
)
@click.option("--year", required=False, help="plot only the data for certain year", type=int)
@click.option(
    "--groupby-category",
    required=False,
    help="group data by category",
    is_flag=True,
)
def plot(
    pelican_conf_path: str = "",
    articles_metadata_path: str = "",
    output_path: str = "trend_plot.html",
    year: int | None = None,
    groupby_category: bool = False,
) -> None:
    """Draw trend plot based on the frequency of new posts"""
    if not pelican_conf_path and not articles_metadata_path:
        print(
            "Neither pelican_conf_path nor articles_metadata_path is provided",
            file=sys.stderr,
        )
        sys.exit(1)

    if (pelican_conf_path and not os.path.exists(pelican_conf_path)) or (
        articles_metadata_path and not os.path.exists(articles_metadata_path)
    ):
        print(
            f"{pelican_conf_path or articles_metadata_path} does not exist",
            file=sys.stderr,
        )
        sys.exit(1)

    if pelican_conf_path:
        data_collector = PelicanArticleDataCollector(pelican_conf_path)
        articles_info = data_collector.extract_articles_info()
    elif articles_metadata_path:
        with open(articles_metadata_path) as metadata_file:
            articles_info = json.load(metadata_file)
    else:
        raise ValueError("Either pelican conf path or metadata path should be provided.")

    data_plotter = PelicanDataPlotter(articles_info)
    data_plotter.draw_trend_plot(output_path, year=year, groupby_category=groupby_category)


@main.command()
@click.argument(
    "pelican_conf_path",
    required=True,
    default="pelicanconf.py",
)
def wordcount(pelican_conf_path: str) -> None:
    """Compute site-wide word count statistics for a pelican project"""
    if not os.path.exists(pelican_conf_path):
        print(f"Configuration file {pelican_conf_path} does not exists", file=sys.stderr)
        sys.exit(1)

    data_collector = PelicanArticleDataCollector(pelican_conf_path)
    # `PELICAN_STAT_INCLUDE_CODE_BLOCKS` (default `False`, matching
    # `ArticleWordCountAggregator`'s own default): read from the project's
    # `pelicanconf.py`-derived settings (same settings dict
    # `PelicanArticleDataCollector` already built its `pelican_instance`
    # from) so this CLI command respects the same site-level setting the
    # `{% writing_stats %}` plugin path does. No separate `--flag` for
    # this: unlike `pelican_conf_path` itself, none of this tool's other
    # `PELICAN_STAT_*` settings (`PELICAN_STAT_SHORTCODE`,
    # `PELICAN_STAT_LABELS`) have a CLI-flag override either -- they're all
    # configured exclusively via `pelicanconf.py`, and adding one knob a
    # different way than every sibling setting would be an inconsistency,
    # not a convenience.
    include_block_code = bool(
        data_collector.pelican_instance.settings.get("PELICAN_STAT_INCLUDE_CODE_BLOCKS", False)
    )
    aggregator = ArticleWordCountAggregator(data_collector.articles, include_block_code=include_block_code)
    result = aggregator.compute()
    print(json.dumps(result, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    main()
