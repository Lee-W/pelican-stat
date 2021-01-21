import pytest
import os

from pelican_stat import plotter

sample_articles_info = [
    {
        "timestamp": 1611043920.0,
        "category": "Testing",
        "authors": ["Lee-W"],
        "reader": "markdown",
        "status": "published",
        "tags": ["test_tag"],
        "timezone": "Asia/Taipei",
        "title": "this is title",
    }
]


@pytest.mark.parametrize(
    "year, groupby_category", ((None, False), (2020, False), (2020, True), (None, True))
)
def test_draw_trend_plot(tmpdir, year, groupby_category):
    """Test whether all the valid parameter combination can generate plot

    Note that this test does not check the content of the plot
    """
    with tmpdir.as_cwd():
        output_path = tmpdir / "test_result.html"

        data_plotter = plotter.PelicanDataPlotter(sample_articles_info)
        data_plotter.draw_trend_plot(
            output_path, year=year, groupby_category=groupby_category
        )
        assert os.path.exists(output_path)
        os.remove(output_path)
