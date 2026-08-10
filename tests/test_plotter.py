from __future__ import annotations

import os

import pytest

from pelican.plugins.stat import plotter

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
    ("year", "groupby_category"), [(None, False), (2020, False), (2020, True), (None, True)]
)
def test_draw_trend_plot(tmpdir, year, groupby_category):
    """Test whether all the valid parameter combination can generate plot

    Note that this test does not check the content of the plot
    """
    with tmpdir.as_cwd():
        output_path = tmpdir / "test_result.html"

        data_plotter = plotter.PelicanDataPlotter(sample_articles_info)
        data_plotter.draw_trend_plot(output_path, year=year, groupby_category=groupby_category)
        assert os.path.exists(output_path)
        os.remove(output_path)


@pytest.mark.parametrize(
    ("year", "groupby_category"), [(None, False), (2020, False), (2020, True), (None, True)]
)
def test_render_trend_plot_html(year, groupby_category):
    """render_trend_plot_html should return a plotly HTML fragment, not a full page

    It must not embed a full <html> document skeleton, and must not reference
    the plotly CDN (plotly.js is expected to be self-hosted).
    """
    data_plotter = plotter.PelicanDataPlotter(sample_articles_info)
    html = data_plotter.render_trend_plot_html(year=year, groupby_category=groupby_category)

    assert isinstance(html, str)
    assert "<html>" not in html
    assert "cdn.plot.ly" not in html
