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
@click.argument(
    "pelican_conf_path", required=True, default="pelicanconf.py",
)
@click.argument(
    "output_path", required=True, default="trend_plot.html",
)
@click.option(
    "--year", required=False, help="plot only the data for certain year", type=int
)
@click.option(
    "--groupby-category",
    required=False,
    help="whether to group plot by category",
    is_flag=True,
)
def plot(
    pelican_conf_path: str,
    output_path: str,
    year: Optional[int] = None,
    groupby_category: bool = False,
) -> None:
    """Draw trend plot based on the frequency of new posts"""
    if not os.path.exists(pelican_conf_path):
        print(
            f"Configuration file {pelican_conf_path} does not exists", file=sys.stderr
        )
        sys.exit(1)

    data_collector = PelicanArticleDataCollector(pelican_conf_path)
    articles_info = data_collector.extract_articles_info()

    data_plotter = PelicanDataPlotter(articles_info)
    data_plotter.draw_trend_plot(
        output_path, year=year, groupby_category=groupby_category
    )


if __name__ == "__main__":
    main()
