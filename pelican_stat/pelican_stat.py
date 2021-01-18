import json

import pelican

settings = pelican.read_settings("pelicanconf.py")

cls = settings["PELICAN_CLASS"]
if isinstance(cls, str):
    module, cls_name = cls.rsplit(".", 1)
    module = __import__(module)
    cls = getattr(module, cls_name)

pelican_instance = cls(settings)
article_generator_cls = pelican_instance.get_generator_classes()[0]
# _get_generator_classes for >= 4.5.2


context = pelican_instance.settings.copy()
context["generated_content"] = {}
context["static_links"] = set()
context["static_content"] = {}
context["localsiteurl"] = pelican_instance.settings["SITEURL"]

article_generator = article_generator_cls(
    context=context,
    settings=settings,
    path=pelican_instance.path,
    theme=pelican_instance.theme,
    output_path=pelican_instance.output_path,
)
article_generator.generate_context()


info = []
for article in article_generator.articles:
    info.append(
        {
            "timestampe": article.date.timestamp(),
            "category": article.category.name,
            "source": "main_blog",
        }
    )

with open("result.json", "w") as f:
    json.dump(info, f, ensure_ascii=False, indent=4)
