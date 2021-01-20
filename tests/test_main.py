from click.testing import CliRunner

from pelican_stat.__main__ import main
from pelican_stat.collector import PelicanArticleDataCollector


class TestCollectCommand:
    def test_normal_case(_, mocker):
        mocked_export_method = mocker.patch.object(
            PelicanArticleDataCollector, "export"
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["collect", "tests/sample_pelican_project/pelicanconf.py"]
        )
        assert result.exit_code == 0
        mocked_export_method.assert_called_once()

    def test_pelican_conf_not_found(_):
        runner = CliRunner()
        result = runner.invoke(main, ["collect"])
        assert result.exit_code == 1
