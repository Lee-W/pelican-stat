import pelican

from pelican_stat import collector


def test_get_pelican_instance():
    pelican_instance = collector.PelicanArticleDataCollector._get_pelican_instance(
        "tests/sample_pelican_project/pelicanconf.py"
    )
    assert isinstance(pelican_instance, pelican.Pelican)


def test_collect_articles():
    data_collector = collector.PelicanArticleDataCollector(
        "tests/sample_pelican_project/pelicanconf.py"
    )
    data_collector.collect_articles()

    assert len(data_collector.articles) == 1

    article = data_collector.articles[0]
    assert article.title == "this is title"
    assert article.category.name == "Testing"
    assert article.slug == "this_is_title"


def test_export(tmp_path, data_regression):
    output_path = tmp_path / "result.json"

    data_collector = collector.PelicanArticleDataCollector(
        "tests/sample_pelican_project/pelicanconf.py"
    )
    data_collector.collect_articles()
    data_collector.export(output_path)

    with open(output_path, "r") as output_file:
        output_data = output_file.read()

    data_regression.check(output_data)
