from __future__ import annotations

import json
from pathlib import Path

import pelican


class PelicanArticleDataCollector:
    def __init__(self, pelican_conf_path: str) -> None:
        self.pelican_instance = self._get_pelican_instance(pelican_conf_path)
        self.articles: list[pelican.contents.Article] = []
        self.collect_articles()

    @staticmethod
    def _get_pelican_instance(conf_path: str) -> pelican.Pelican:
        settings = pelican.read_settings(conf_path)
        settings["PLUGINS"] = []
        settings["MARKDOWN"] = {}

        cls = settings["PELICAN_CLASS"]
        if isinstance(cls, str):
            module_name, cls_name = cls.rsplit(".", 1)
            module = __import__(module_name)
            cls = getattr(module, cls_name)

        return cls(settings)

    def collect_articles(self) -> None:
        article_generator_cls = self.pelican_instance._get_generator_classes()[0]

        context = self.pelican_instance.settings.copy()
        context["generated_content"] = {}
        context["static_links"] = set()
        context["static_content"] = {}
        context["localsiteurl"] = self.pelican_instance.settings["SITEURL"]

        article_generator = article_generator_cls(
            context=context,
            settings=self.pelican_instance.settings,
            path=self.pelican_instance.path,
            theme=self.pelican_instance.theme,
            output_path=self.pelican_instance.output_path,
        )
        article_generator.generate_context()
        self.articles = article_generator.articles

    def extract_articles_info(self) -> list[dict[str, str | int]]:
        articles_info: list[dict[str, str | int]] = [
            {
                "timestamp": article.date.timestamp(),
                "category": article.category.name,
                "authors": [author.name for author in article.authors],  # type: ignore
                "reader": article.reader,
                "status": article.status,
                "tags": [tag.name for tag in article.tags],  # type: ignore
                "timezone": str(article.timezone),
                "title": article.title,
            }
            for article in self.articles
        ]
        return articles_info

    def export(self, output_path: Path | str) -> None:
        articles_info = self.extract_articles_info()
        with open(output_path, "w") as f:
            json.dump(articles_info, f, ensure_ascii=False, indent=4)
