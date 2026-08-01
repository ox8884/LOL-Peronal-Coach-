"""Click-based CLI for LoL Personal Coach."""

from __future__ import annotations

import sys
from io import TextIOWrapper

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lol_coach import __app_name__, __version__
from lol_coach.analysis.coach import CoachEngine
from lol_coach.analysis.stats import format_recent_form
from lol_coach.config import (
    ensure_configured,
    load_settings,
    prompt_for_api_key,
    save_api_key,
    save_player,
)
from lol_coach.modes import MODE_ARAM, MODE_SUMMONERS_RIFT, normalize_mode
from lol_coach.riot.client import RiotAPIError, RiotClient
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer
from lol_coach.ugg.client import UGGClient, UGGError, normalize_role


def _make_console_output_tolerant() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(errors="replace")


_make_console_output_tolerant()

console = Console()


def _parse_riot_id(riot_id: str) -> tuple[str, str]:
    if "#" not in riot_id:
        raise click.ClickException("Riot ID는 Name#TAG 형식이어야 합니다")
    name, tag = riot_id.split("#", 1)
    name, tag = name.strip(), tag.strip()
    if not name or not tag:
        raise click.ClickException("Riot ID는 Name#TAG 형식이어야 합니다")
    return name, tag


def _client_from_settings() -> tuple[RiotClient, object]:
    settings = ensure_configured(interactive=True)
    # allow slightly weird keys if user forced save
    client = RiotClient(
        api_key=settings.riot_api_key,
        platform=settings.platform,
        region=settings.region,
    )
    return client, settings


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name=__app_name__)
@click.option("-v", "--verbose", is_flag=True, help="디버그 로그 출력 (네트워크 재시도·캐시)")
def main(verbose: bool) -> None:
    """롤 개인 코치 — Riot 전적 + u.gg 메타 맞춤 코칭 CLI."""
    from lol_coach.log import setup_logging

    setup_logging(verbose=verbose)


@main.command("setup")
@click.option("--api-key", default=None, help="Riot API 키 (RGAPI-...)")
@click.option("--riot-id", default=None, help="기본 소환사 (예: 소환사명#KR1)")
@click.option("--platform", default="na1", show_default=True, help="서버 코드 (na1, kr …)")
@click.option("--force", is_flag=True, help="기존 API 키 덮어쓰기")
def setup_cmd(
    api_key: str | None, riot_id: str | None, platform: str, force: bool
) -> None:
    """Riot API 키와 기본 소환사를 설정합니다 (.env 저장)."""
    if api_key:
        path = save_api_key(api_key)
        console.print(f"[green]API 키 저장 완료 → {path}[/green]")
    else:
        prompt_for_api_key(force=force)

    settings = load_settings()
    if riot_id:
        name, tag = _parse_riot_id(riot_id)
    else:
        name, tag = settings.game_name, settings.tag_line
        console.print(
            f"기본 소환사: [cyan]{name}#{tag}[/cyan] / 서버 [cyan]{platform}[/cyan]"
        )
        if click.confirm("기본 소환사를 바꿀까요?", default=False):
            riot_id = click.prompt("Riot ID (Name#TAG)", default=f"{name}#{tag}")
            name, tag = _parse_riot_id(riot_id)
            platform = click.prompt("서버 (platform)", default=platform)

    path = save_player(name, tag, platform=platform)
    console.print(
        Panel.fit(
            f"설정 완료\n"
            f"  소환사 : {name}#{tag}\n"
            f"  서버   : {platform}\n"
            f"  설정파일: {path}",
            title="lol-coach 설정",
            border_style="green",
        )
    )


@main.command("profile")
@click.option("--riot-id", default=None, help="소환사 (Name#TAG)")
@click.option("--platform", default=None, help="서버 (na1, kr …)")
@click.option("--count", default=10, show_default=True, help="조회할 최근 경기 수")
@click.option(
    "--queue",
    default=None,
    type=int,
    help="큐 필터 (420 솔랭, 440 자랭, 450 칼바람, 2400 아수라장 …)",
)
@click.option(
    "--include-aram/--sr-only",
    default=True,
    show_default=True,
    help="칼바람/아수라장 포함 여부 (--sr-only 면 협곡만)",
)
def profile_cmd(
    riot_id: str | None,
    platform: str | None,
    count: int,
    queue: int | None,
    include_aram: bool,
) -> None:
    """Riot ID → PUUID + 최근 전적 분석 (모드별 구분)."""
    client, settings = _client_from_settings()
    if platform:
        client.set_platform(platform)

    if riot_id:
        game_name, tag_line = _parse_riot_id(riot_id)
    else:
        game_name, tag_line = settings.game_name, settings.tag_line

    queues = None
    if queue is None and not include_aram:
        from lol_coach.modes import queues_for_mode

        queues = queues_for_mode(MODE_SUMMONERS_RIFT)

    with console.status(f"{game_name}#{tag_line} 조회 중..."):
        try:
            profile = client.resolve_player(game_name, tag_line)
            form = client.get_recent_form(
                profile, count=count, queue=queue, queues=queues
            )
            ranks: list = []
            try:
                ranks = client.get_league_entries(profile.puuid)
            except RiotAPIError:
                pass  # 랭크 조회 실패 시에도 전적은 그대로 표시
        except RiotAPIError as exc:
            raise click.ClickException(str(exc)) from exc

    if ranks:
        from lol_coach.display import rank_line

        console.print(rank_line(ranks))

    # 이미 한글 헤더가 본문에 포함되어 있어 Panel 테두리만 사용
    console.print(format_recent_form(form))


@main.command("live")
@click.option("--riot-id", default=None, help="소환사 (Name#TAG)")
@click.option("--platform", default=None, help="서버 코드")
def live_cmd(riot_id: str | None, platform: str | None) -> None:
    """현재 인게임 여부 확인."""
    client, settings = _client_from_settings()
    if platform:
        client.set_platform(platform)

    if riot_id:
        game_name, tag_line = _parse_riot_id(riot_id)
    else:
        game_name, tag_line = settings.game_name, settings.tag_line

    with console.status("관전 API 확인 중..."):
        try:
            profile = client.resolve_player(game_name, tag_line)
            game = client.get_active_game(profile.puuid)
        except RiotAPIError as exc:
            raise click.ClickException(str(exc)) from exc

    if not game:
        console.print(
            f"[yellow]{profile.riot_id} 님은 현재 게임이 없습니다.[/yellow]"
        )
        return

    dd = DataDragon(language="ko_KR")
    table = Table(title=f"진행 중 게임 — {profile.riot_id}")
    table.add_column("진영")
    table.add_column("챔피언")
    table.add_column("소환사")
    for p in game.participants:
        side = "블루" if p.get("teamId") == 100 else "레드"
        champ = dd.champion_name(int(p.get("championId") or 0))
        name = p.get("riotId") or p.get("summonerName") or "?"
        mine = " ← 나" if p.get("puuid") == profile.puuid else ""
        table.add_row(side, champ, f"{name}{mine}")

    console.print(table)
    console.print(
        f"모드: {game.game_mode} | 큐: {game.game_queue_config_id} | "
        f"경과: {game.game_length}초"
    )


@main.command("meta")
@click.argument("champion")
@click.option(
    "--mode",
    "-m",
    "mode",
    default=MODE_SUMMONERS_RIFT,
    show_default=True,
    type=click.Choice(
        [MODE_SUMMONERS_RIFT, MODE_ARAM, "sr", "mayhem"],
        case_sensitive=False,
    ),
    help="모드: summoners_rift(협곡) | aram(칼바람·아수라장)",
)
@click.option(
    "--role",
    "-r",
    default="mid",
    show_default=True,
    help="협곡 포지션: top/jungle/mid/adc/support",
)
def meta_cmd(champion: str, mode: str, role: str) -> None:
    """현재 패치 u.gg 메타 빌드 (협곡 또는 칼바람)."""
    try:
        mode_n = normalize_mode(mode)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    ugg = UGGClient()
    dd = DataDragon(language="ko_KR")
    resolved = dd.resolve_champion(champion)
    # 내부 키는 영문 id 유지 (u.gg slug), 표시는 한글
    if resolved:
        champ_name = resolved["id"]
        champ_display = resolved["name"]
    else:
        champ_name = champion
        champ_display = champion

    from lol_coach.static.i18n import ROLE_KO

    label = (
        "칼바람"
        if mode_n == MODE_ARAM
        else ROLE_KO.get(role.upper(), role)
    )
    with console.status(f"u.gg 메타 불러오는 중 — {champ_display} ({label})..."):
        try:
            if mode_n == MODE_SUMMONERS_RIFT:
                normalize_role(role)
            build = ugg.get_champion_build(
                champ_name, role=role, mode=mode_n
            )
            # 챔피언 표시명은 한글 쪽으로
            build.champion = champ_display if resolved else build.champion
        except (UGGError, Exception) as exc:
            raise click.ClickException(str(exc)) from exc

    engine = CoachEngine(dd)
    report = engine.compare(build, [], role=build.role)
    console.print(report.render())


@main.command("coach")
@click.argument("champion")
@click.option(
    "--mode",
    "-m",
    "mode",
    default=MODE_SUMMONERS_RIFT,
    show_default=True,
    type=click.Choice(
        [MODE_SUMMONERS_RIFT, MODE_ARAM, "sr", "mayhem"],
        case_sensitive=False,
    ),
    help="모드: summoners_rift(협곡) | aram(칼바람·아수라장)",
)
@click.option(
    "--role",
    "-r",
    default="mid",
    show_default=True,
    help="협곡 포지션 (칼바람 모드에선 무시)",
)
@click.option("--riot-id", default=None, help="소환사 (Name#TAG)")
@click.option("--platform", default=None, help="서버 코드")
@click.option(
    "--lookback",
    default=20,
    show_default=True,
    help="해당 챔피언 기준 최근 경기 수 (모드 필터 적용)",
)
def coach_cmd(
    champion: str,
    mode: str,
    role: str,
    riot_id: str | None,
    platform: str | None,
    lookback: int,
) -> None:
    """메타 빌드 + 내 전적 → 맞춤 코칭."""
    try:
        mode_n = normalize_mode(mode)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    client, settings = _client_from_settings()
    if platform:
        client.set_platform(platform)

    if riot_id:
        game_name, tag_line = _parse_riot_id(riot_id)
    else:
        game_name, tag_line = settings.game_name, settings.tag_line

    dd = DataDragon(language="ko_KR")
    resolved = dd.resolve_champion(champion)
    if not resolved:
        console.print(
            f"[yellow]경고: 챔피언 '{champion}'을(를) Data Dragon에서 "
            "찾지 못해 입력값을 그대로 씁니다.[/yellow]"
        )
        champ_display = champion
        champ_key = champion
    else:
        champ_display = resolved["name"]  # 한글
        champ_key = resolved["id"]  # 영문 키 (매치/u.gg)

    ugg = UGGClient()
    from lol_coach.static.i18n import ROLE_KO

    status_label = (
        "칼바람·아수라장"
        if mode_n == MODE_ARAM
        else ROLE_KO.get(role.upper(), role)
    )
    with console.status(
        f"{champ_display} ({status_label}) 메타·전적 불러오는 중..."
    ):
        try:
            profile = client.resolve_player(game_name, tag_line)
            my_games = client.get_champion_matches(
                profile,
                champ_key,
                lookback=lookback,
                mode=mode_n,
            )
            # Riot match championName is English key — already matched via champ_key
            build = ugg.get_champion_build(
                champ_key, role=role, mode=mode_n
            )
            build.champion = champ_display
        except (RiotAPIError, UGGError) as exc:
            raise click.ClickException(str(exc)) from exc

    engine = CoachEngine(dd)
    report = engine.compare(build, my_games, role=build.role)
    console.print(report.render())


@main.command("gui")
def gui_cmd() -> None:
    """카운터픽 데스크탑 GUI 실행 (CustomTkinter)."""
    try:
        from lol_coach.gui.app import run_app
    except ImportError as exc:
        raise click.ClickException(
            "customtkinter 가 필요합니다.  pip install customtkinter"
        ) from exc
    run_app()


@main.command("pool")
@click.option("--riot-id", default=None, help="소환사 (Name#TAG)")
@click.option("--platform", default=None, help="서버 (na1, kr …)")
@click.option("--count", default=30, show_default=True, help="분석할 최근 경기 수")
def pool_cmd(riot_id: str | None, platform: str | None, count: int) -> None:
    """챔피언 풀 진단 — 집중/유지/정리 추천."""
    from lol_coach.analysis.pool import diagnose_pool

    client, settings = _client_from_settings()
    if platform:
        client.set_platform(platform)

    if riot_id:
        game_name, tag_line = _parse_riot_id(riot_id)
    else:
        game_name, tag_line = settings.game_name, settings.tag_line

    with console.status(f"{game_name}#{tag_line} 챔피언 풀 분석 중..."):
        try:
            profile = client.resolve_player(game_name, tag_line)
            form = client.get_recent_form(profile, count=count)
        except RiotAPIError as exc:
            raise click.ClickException(str(exc)) from exc

    loc = get_localizer()
    loc.ensure_loaded()
    report = diagnose_pool(form)
    console.print(
        f"[bold]챔피언 풀 진단[/bold] — {profile.riot_id} · "
        f"최근 {report.total_games}게임 · 전체 승률 {report.overall_wr}%"
    )
    table = Table(show_header=True)
    table.add_column("챔피언")
    table.add_column("게임", justify="right")
    table.add_column("승률", justify="right")
    table.add_column("보정", justify="right")
    table.add_column("KDA", justify="right")
    table.add_column("판정")
    table.add_column("메모")
    color = {"집중": "green", "유지": "white", "표본 부족": "dim", "정리 검토": "yellow"}
    for e in report.entries:
        name = loc.champion(e.champion_name) or e.champion_name
        table.add_row(
            name,
            str(e.games),
            f"{e.winrate}%",
            f"{e.adjusted_wr}%",
            f"{e.avg_kda}",
            f"[{color.get(e.verdict, 'white')}]{e.verdict}[/]",
            e.reason,
        )
    console.print(table)


@main.command("export")
@click.option("--riot-id", default=None, help="소환사 (Name#TAG)")
@click.option("--platform", default=None, help="서버 (na1, kr …)")
@click.option("--count", default=20, show_default=True, help="내보내기할 최근 경기 수")
@click.option(
    "--format",
    "fmt",
    default="csv",
    show_default=True,
    type=click.Choice(["csv", "json"], case_sensitive=False),
    help="출력 형식",
)
@click.option("--out", default=None, help="출력 파일 경로 (기본: 현재 작업 디렉터리)")
def export_cmd(
    riot_id: str | None,
    platform: str | None,
    count: int,
    fmt: str,
    out: str | None,
) -> None:
    """최근 전적을 CSV/JSON 파일로 내보내기."""
    from lol_coach.analysis.export import (
        export_matches_csv,
        export_matches_json,
    )

    client, settings = _client_from_settings()
    if platform:
        client.set_platform(platform)

    if riot_id:
        game_name, tag_line = _parse_riot_id(riot_id)
    else:
        game_name, tag_line = settings.game_name, settings.tag_line

    with console.status(f"{game_name}#{tag_line} 전적 조회 중..."):
        try:
            profile = client.resolve_player(game_name, tag_line)
            form = client.get_recent_form(profile, count=count)
        except RiotAPIError as exc:
            raise click.ClickException(str(exc)) from exc

    if not out:
        safe = f"{game_name}_{tag_line}".replace(" ", "_")
        out = f"lol_coach_matches_{safe}.{fmt.lower()}"
    if fmt.lower() == "json":
        path = export_matches_json(form, out)
    else:
        path = export_matches_csv(form, out)
    console.print(f"[green]내보내기 완료[/green] → {path}  ({form.games}게임)")


@main.command("test-key")
def test_key_cmd() -> None:
    """설정된 Riot API 키가 동작하는지 확인합니다."""
    client, settings = _client_from_settings()
    with console.status("API 키 검증 중..."):
        try:
            profile = client.resolve_player(settings.game_name, settings.tag_line)
        except RiotAPIError as exc:
            if exc.status_code in (401, 403):
                raise click.ClickException(
                    f"API 키가 거부되었습니다 ({exc.status_code}). "
                    "https://developer.riotgames.com/ 에서 새 키를 발급하세요."
                ) from exc
            raise click.ClickException(str(exc)) from exc

    console.print(
        f"[green]정상[/green] — {profile.riot_id}  PUUID={profile.puuid[:12]}…"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Aborted.[/dim]")
        sys.exit(130)
