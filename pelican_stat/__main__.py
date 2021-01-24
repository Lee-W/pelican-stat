import json
import os
import sys
from typing import Optional

import click

from pelican_stat.collector import PelicanArticleDataCollector
from pelican_stat.plotter import PelicanDataPlotter


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument(
    "pelican_conf_path", required=True, default="pelicanconf.py",
)
@click.argument(
    "output_path", required=True, default="article_metadata.json",
)
def collect(pelican_conf_path: str, output_path: str) -> None:
    """Collect data from pelican project and export article metadata"""
    if not os.path.exists(pelican_conf_path):
        print(
            f"Configuration file {pelican_conf_path} does not exists", file=sys.stderr
        )
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
@click.option(
    "--year", required=False, help="plot only the data for certain year", type=int
)
@click.option(
    "--groupby-category", required=False, help="group data by categoyy", is_flag=True,
)
def plot(
    pelican_conf_path: str = None,
    articles_metadata_path: str = None,
    output_path: str = "trend_plot.html",
    year: Optional[int] = None,
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
        with open(articles_metadata_path, "r") as metadata_file:
            articles_info = json.load(metadata_file)

    data_plotter = PelicanDataPlotter(articles_info)
    data_plotter.draw_trend_plot(
        output_path, year=year, groupby_category=groupby_category
    )


if __name__ == "__main__":
    main()
