"""Chart files for the Reels pipeline: `cricket chart batting --player "V Kohli" --aspect 9:16 --png card.png`."""

from pathlib import Path

from . import api


class EmptyResult(ValueError):
    pass


def render(
    module_id: str,
    aspect: str = "9:16",
    focus: str | None = None,
    png: Path | None = None,
    html: Path | None = None,
    db_path=None,
    **params,
):
    """Run the module, build its video figure, write the PNG and/or HTML. Returns (figure, result).
    Raises EmptyResult (no rows), ValueError (bad params / aspect / module without a video chart)."""
    from .viz import video

    if module_id not in video.module_ids():
        raise ValueError(
            f"No video chart for {module_id!r}. Available: {', '.join(video.module_ids())}"
        )
    result = api.run(module_id, db_path=db_path, **params)
    if result.data.empty:
        raise EmptyResult(
            f"{module_id} returned no rows for {result.meta['params']}; nothing to draw. "
            f"Check the names with `cricket resolve`."
        )
    fig = video.video_figure(module_id, result, aspect, focus)
    for p in (png, html):
        if p:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
    if png:
        fig.write_image(
            str(png), scale=1
        )  # 1080 px wide at scale 1 (kaleido drives the installed Edge)
    if html:
        fig.write_html(str(html), include_plotlyjs=True)
    return fig, result
