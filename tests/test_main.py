from __future__ import annotations

import json

from click.testing import CliRunner

from pelican.plugins.stat.__main__ import main
from pelican.plugins.stat.collector import PelicanArticleDataCollector
from pelican.plugins.stat.plotter import PelicanDataPlotter


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


class TestWordcountCommand:
    def _write_project(self, project_dir, *, include_code_blocks: bool | None = None):
        """A minimal real pelicanconf.py + one article containing an
        indented (4-space) code block, which Python-Markdown's built-in
        code block handling renders as `<pre><code>...` -- used to prove
        `PELICAN_STAT_INCLUDE_CODE_BLOCKS`, read from a REAL pelicanconf.py
        file via `pelican.read_settings()` (not injected in-process), is
        actually respected by the `wordcount` CLI command end-to-end.
        `include_code_blocks=None` omits the setting entirely (unspecified
        case)."""
        project_dir.mkdir(parents=True)
        content_dir = project_dir / "content"
        content_dir.mkdir()
        (content_dir / "article.md").write_text(
            "Title: t\nDate: 2021-01-19 16:12\nCategory: Testing\nSlug: t\n\n"
            "abc\n\n    def foo():\n        pass\n",
            encoding="utf-8",
        )
        conf_lines = [
            "AUTHOR = 'test'",
            "SITENAME = 'test'",
            "SITEURL = ''",
            f"PATH = {str(content_dir)!r}",
            "TIMEZONE = 'Asia/Taipei'",
            "DEFAULT_LANG = 'zh'",
        ]
        if include_code_blocks is not None:
            conf_lines.append(f"PELICAN_STAT_INCLUDE_CODE_BLOCKS = {include_code_blocks!r}")
        conf_path = project_dir / "pelicanconf.py"
        conf_path.write_text("\n".join(conf_lines) + "\n", encoding="utf-8")
        return conf_path

    def test_respects_include_code_blocks_setting(self, tmp_path):
        """Real CLI invocations (via `CliRunner`, which goes through
        `PelicanArticleDataCollector` -> `pelican.read_settings()` from an
        actual file on disk) with the setting unspecified vs. explicitly
        `True` must produce a strictly larger `total_char_count` in the
        `True` case -- proving the CLI path (not just the plugin/settings
        path already covered in `test_stat.py`) reads and respects this
        setting."""
        runner = CliRunner()

        conf_default = self._write_project(tmp_path / "default")
        result_default = runner.invoke(main, ["wordcount", str(conf_default)])
        assert result_default.exit_code == 0
        stats_default = json.loads(result_default.output)

        conf_true = self._write_project(tmp_path / "true", include_code_blocks=True)
        result_true = runner.invoke(main, ["wordcount", str(conf_true)])
        assert result_true.exit_code == 0
        stats_true = json.loads(result_true.output)

        assert stats_true["total_char_count"] > stats_default["total_char_count"]
        assert stats_true["total_char_count"] - stats_default["total_char_count"] >= 20


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
