from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go


class PelicanDataPlotter:
    def __init__(self, articles_info: list[dict[str, int | str]]):
        self.df = pd.DataFrame(articles_info)
        self.df.timestamp = pd.to_datetime(self.df.timestamp, unit="s")
        self.df.sort_values("timestamp", inplace=True)
        self.df.reset_index(inplace=True, drop=True)
        self.df.index += 1

    def _build_figure(self, *, year: int | None = None, groupby_category: bool = False) -> go.Figure:
        if year:
            plot_df = self.df[
                (datetime(year, 1, 1) <= self.df.timestamp) & (self.df.timestamp <= datetime(year, 12, 31))
            ]
            plot_df.reset_index(inplace=True, drop=True)
            plot_df.index += 1
        else:
            plot_df = self.df.copy()

        fig = go.Figure()
        if groupby_category:
            for category, cate_df in plot_df.groupby("category"):
                cate_df.reset_index(inplace=True, drop=True)
                cate_df.index += 1
                fig.add_trace(
                    go.Scatter(
                        x=cate_df.timestamp,
                        y=cate_df.index,
                        mode="lines+markers",
                        name=category,
                    )
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=plot_df.timestamp,
                    y=plot_df.index,
                    mode="lines+markers",
                )
            )
        return fig

    def draw_trend_plot(
        self, output_path: str, *, year: int | None = None, groupby_category: bool = False
    ) -> None:
        fig = self._build_figure(year=year, groupby_category=groupby_category)
        fig.write_html(output_path)

    def render_trend_plot_html(self, *, year: int | None = None, groupby_category: bool = False) -> str:
        fig = self._build_figure(year=year, groupby_category=groupby_category)
        html: str = fig.to_html(full_html=False, include_plotlyjs=False)
        return html
