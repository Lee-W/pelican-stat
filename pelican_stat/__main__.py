import os

import click

from pelican_stat.collector import PelicanArticleDataCollector


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
        raise Exception(f"Configuration file {pelican_conf_path} does not exists")

    pelican_instance = PelicanArticleDataCollector(pelican_conf_path)
    pelican_instance.collect_articles()
    pelican_instance.export(output_path)


if __name__ == "__main__":
    main()
