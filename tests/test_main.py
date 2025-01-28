from __future__ import annotations

from click.testing import CliRunner

from pelican_stat.__main__ import main
from pelican_stat.collector import PelicanArticleDataCollector
from pelican_stat.plotter import PelicanDataPlotter


class TestCollectCommand:
    def test_normal_case(self, mocker):
        mocked_export_method = mocker.patch.object(PelicanArticleDataCollector, "export")

        runner = CliRunner()
        result = runner.invoke(main, ["collect", "tests/sample_pelican_project/pelicanconf.py"])
        assert result.exit_code == 0
        mocked_export_method.assert_called_once()

    def test_pelican_conf_not_found(self):
        runner = CliRunner()
        result = runner.invoke(main, ["collect"])
        assert result.exit_code == 1


class TestPlotCommand:
    def test_normal_case(self, mocker):
        mocked_draw_method = mocker.patch.object(PelicanDataPlotter, "draw_trend_plot")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "plot",
                "--pelican-conf-path",
                "tests/sample_pelican_project/pelicanconf.py",
            ],
        )
        assert result.exit_code == 0
        mocked_draw_method.assert_called_once()
