from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .curator import dedupe_by_uri, filter_tracks, sort_for_playlist
from .library import DEFAULT_LIBRARY_PATH, Library
from .models import PlaylistRecord, Track

console = Console()


def _load_library(path: Path) -> Library:
    return Library(path=path).load()


@click.group()
@click.option(
    "--library",
    "library_path",
    default=str(DEFAULT_LIBRARY_PATH),
    show_default=True,
    type=click.Path(path_type=Path),
    help="로컬 라이브러리 JSON 경로",
)
@click.pass_context
def cli(ctx: click.Context, library_path: Path) -> None:
    """pb — 좋아하는 음악을 큐레이션해 Spotify 플레이리스트로 만든다."""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["library_path"] = library_path


@cli.command()
@click.pass_context
def auth(ctx: click.Context) -> None:
    """Spotify OAuth 로그인."""
    from .spotify_client import SpotifyClient

    sp = SpotifyClient()
    user = sp.authenticate()
    console.print(f"[green]로그인 성공[/green]: {user.get('display_name')} ({user.get('id')})")


@cli.command()
@click.option("--limit", type=int, default=None, help="가져올 최대 곡 수 (기본: 전체)")
@click.pass_context
def pull(ctx: click.Context, limit: Optional[int]) -> None:
    """Spotify의 '좋아요'와 내 플레이리스트를 로컬에 동기화."""
    from .spotify_client import SpotifyClient

    lib = _load_library(ctx.obj["library_path"])
    sp = SpotifyClient()

    console.print("좋아요 트랙 가져오는 중...")
    liked = sp.pull_liked(limit=limit)
    for t in liked:
        lib.upsert_track(t)
    console.print(f"  → {len(liked)}곡 동기화")

    console.print("플레이리스트 메타 가져오는 중...")
    playlists = sp.pull_playlists()
    for pl in playlists:
        existing = lib.playlists.get(pl["name"])
        criteria = existing.criteria if existing else {}
        lib.upsert_playlist(
            PlaylistRecord(name=pl["name"], spotify_id=pl["id"], criteria=criteria)
        )
    console.print(f"  → {len(playlists)}개 플레이리스트")

    lib.save()
    console.print(f"[green]{ctx.obj['library_path']}에 저장[/green]")


@cli.command()
@click.argument("query", required=False)
@click.option("--tag", "tags", multiple=True, help="부여할 태그 (여러 번 지정 가능)")
@click.option("--rating", type=click.IntRange(0, 5), default=None, help="0-5 평점")
@click.option("--note", default=None, help="메모")
@click.option("--interactive", "-i", is_flag=True, help="태깅 안 된 곡을 순회하며 입력")
@click.pass_context
def tag(
    ctx: click.Context,
    query: Optional[str],
    tags: tuple[str, ...],
    rating: Optional[int],
    note: Optional[str],
    interactive: bool,
) -> None:
    """트랙에 태그·평점·메모를 부여한다."""
    lib = _load_library(ctx.obj["library_path"])

    if interactive:
        _interactive_tag(lib)
        lib.save()
        return

    if not query:
        raise click.UsageError("query 또는 --interactive 중 하나가 필요합니다")

    track = _resolve_track(lib, query)
    if track is None:
        return

    if tags:
        lib.add_tags(track.uri, tags)
    if rating is not None:
        lib.set_rating(track.uri, rating)
    if note is not None:
        lib.set_note(track.uri, note)

    lib.save()
    _print_track_row(track)


def _resolve_track(lib: Library, query: str) -> Optional[Track]:
    """URI/ID로 직접 매치하거나, 부분 문자열로 검색."""
    if query in lib.tracks:
        return lib.tracks[query]
    full_uri = f"spotify:track:{query}"
    if full_uri in lib.tracks:
        return lib.tracks[full_uri]

    q = query.lower()
    matches = [
        t
        for t in lib.tracks.values()
        if q in t.name.lower() or any(q in a.lower() for a in t.artists)
    ]
    if not matches:
        console.print(f"[yellow]매치 없음: {query}[/yellow]")
        return None
    if len(matches) == 1:
        return matches[0]

    console.print(f"여러 매치 발견 ({len(matches)}개):")
    for i, t in enumerate(matches[:20], 1):
        console.print(f"  {i}. {t.display}")
    idx = IntPrompt.ask("번호 선택 (0=취소)", default=0)
    if 1 <= idx <= len(matches):
        return matches[idx - 1]
    return None


def _interactive_tag(lib: Library) -> None:
    untagged = [t for t in lib.tracks.values() if not t.tags]
    if not untagged:
        console.print("[yellow]태깅 안 된 곡이 없습니다[/yellow]")
        return

    console.print(f"태깅 안 된 곡 {len(untagged)}개. (q 입력 시 종료)\n")
    for i, t in enumerate(untagged, 1):
        console.print(f"[bold]{i}/{len(untagged)}[/bold] {t.display}")
        if t.album:
            console.print(f"  앨범: {t.album}")
        raw_tags = Prompt.ask("  태그 (쉼표 구분, 빈 값=건너뜀, q=종료)", default="")
        if raw_tags.strip().lower() == "q":
            break
        if raw_tags.strip():
            lib.add_tags(t.uri, [s.strip() for s in raw_tags.split(",")])
        raw_rating = Prompt.ask("  평점 0-5 (빈 값=건너뜀)", default="")
        if raw_rating.strip():
            try:
                lib.set_rating(t.uri, int(raw_rating))
            except ValueError:
                console.print("  [yellow]평점 형식 오류, 건너뜀[/yellow]")
        raw_note = Prompt.ask("  메모 (빈 값=건너뜀)", default="")
        if raw_note.strip():
            lib.set_note(t.uri, raw_note.strip())
        console.print()


@cli.command(name="list")
@click.option("--tag", "tags", multiple=True, help="필터 태그 (모두 가진 곡)")
@click.option("--any-tag", "any_tags", multiple=True, help="필터 태그 (하나라도 가진 곡)")
@click.option("--min-rating", type=click.IntRange(0, 5), default=None)
@click.option("--limit", type=int, default=50)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    tags: tuple[str, ...],
    any_tags: tuple[str, ...],
    min_rating: Optional[int],
    limit: int,
) -> None:
    """라이브러리를 필터링해 출력."""
    lib = _load_library(ctx.obj["library_path"])
    pool = list(lib.tracks.values())

    if tags:
        pool = filter_tracks(pool, tags=tags, match_all_tags=True)
    if any_tags:
        pool = filter_tracks(pool, tags=any_tags, match_all_tags=False)
    if min_rating is not None:
        pool = filter_tracks(pool, min_rating=min_rating)

    pool = sort_for_playlist(pool)[:limit]

    table = Table(show_lines=False)
    table.add_column("아티스트")
    table.add_column("제목")
    table.add_column("⭐")
    table.add_column("태그")
    for t in pool:
        table.add_row(
            ", ".join(t.artists),
            t.name,
            str(t.rating) if t.rating is not None else "-",
            ", ".join(t.tags),
        )
    console.print(table)
    console.print(f"[dim]{len(pool)}곡 표시 (전체 {len(lib.tracks)}곡)[/dim]")


@cli.command()
@click.option("--seed-tag", "seed_tags", multiple=True, required=True, help="시드 추출 태그")
@click.option("-n", "n", type=int, default=10, show_default=True)
@click.option("--mood", default="", help="Claude에 전달할 분위기 힌트")
@click.option("--max-seeds", type=int, default=15, show_default=True)
@click.pass_context
def recommend(
    ctx: click.Context,
    seed_tags: tuple[str, ...],
    n: int,
    mood: str,
    max_seeds: int,
) -> None:
    """태그 시드 → Claude 추천 → Spotify 검색 매칭."""
    from .claude_client import ClaudeClient
    from .spotify_client import SpotifyClient

    lib = _load_library(ctx.obj["library_path"])
    seeds = filter_tracks(lib.tracks.values(), tags=seed_tags, match_all_tags=False)
    seeds = sort_for_playlist(seeds)[:max_seeds]
    if not seeds:
        console.print(f"[red]시드 태그에 해당하는 곡이 없습니다: {seed_tags}[/red]")
        return

    console.print(f"시드 {len(seeds)}곡으로 Claude 추천 요청 중...")
    claude = ClaudeClient()
    recs = claude.recommend(seeds=seeds, n=n, mood=mood)
    console.print(f"  → 추천 {len(recs)}건 수신\n")

    sp = SpotifyClient()
    table = Table(title="Claude 추천 → Spotify 매칭")
    table.add_column("아티스트")
    table.add_column("제목")
    table.add_column("Spotify")
    table.add_column("이유", overflow="fold")
    for r in recs:
        match = sp.search_track(r.search_query())
        spotify_cell = match.uri if match else "[red]매칭 실패[/red]"
        table.add_row(r.artist, r.title, spotify_cell, r.reason)
    console.print(table)


@cli.command()
@click.option("--limit", type=int, default=None, help="분류할 최대 곡 수 (기본: 전체 좋아요)")
@click.option("--categories", "num_categories", type=int, default=None, help="카테고리 개수 (기본: Claude가 자동)")
@click.option("--style", "style_hint", default="", help="분류 스타일 힌트 (예: '무드 위주', '계절별')")
@click.option("--prefix", default="", help="생성될 플리 이름 앞에 붙일 접두사 (예: 'AI/ ')")
@click.option("--dry-run", is_flag=True, help="Spotify에 생성하지 않고 미리보기만")
@click.option("--public", is_flag=True, help="공개 플레이리스트로 생성")
@click.pass_context
def auto(
    ctx: click.Context,
    limit: Optional[int],
    num_categories: Optional[int],
    style_hint: str,
    prefix: str,
    dry_run: bool,
    public: bool,
) -> None:
    """좋아요를 통째로 Claude에 보내 자동 분류하고 여러 플리를 한번에 생성한다."""
    from .claude_client import ClaudeClient
    from .spotify_client import SpotifyClient

    sp = SpotifyClient()

    console.print("Spotify 좋아요 가져오는 중...")
    tracks = sp.pull_liked(limit=limit)
    if not tracks:
        console.print("[red]좋아요 곡이 없습니다[/red]")
        return
    console.print(f"  → {len(tracks)}곡 수집")

    if len(tracks) > 1500:
        console.print(
            f"[yellow]경고: {len(tracks)}곡은 한 번에 처리하기 많습니다. "
            "`--limit 1000` 같이 줄여서 여러 번 돌리는 걸 권장[/yellow]"
        )
        if not Confirm.ask("그래도 진행할까요?", default=False):
            return

    console.print("Claude에 분류 요청 중... (수십 초 걸릴 수 있음)")
    claude = ClaudeClient()
    categories = claude.classify_tracks(
        tracks=tracks,
        num_categories=num_categories,
        style_hint=style_hint,
    )

    if not categories:
        console.print("[red]Claude가 카테고리를 만들지 못했습니다[/red]")
        return

    # 미리보기
    table = Table(title=f"자동 분류 결과 ({len(categories)}개 카테고리)")
    table.add_column("플리 이름")
    table.add_column("설명", overflow="fold")
    table.add_column("곡수", justify="right")
    table.add_column("샘플", overflow="fold")

    uri_to_track = {t.uri: t for t in tracks}
    for cat in categories:
        sample = " / ".join(
            uri_to_track[u].display for u in cat.track_uris[:3] if u in uri_to_track
        )
        table.add_row(
            f"{prefix}{cat.name}",
            cat.description,
            str(len(cat.track_uris)),
            sample,
        )
    console.print(table)

    total = sum(len(c.track_uris) for c in categories)
    console.print(f"[dim]총 {total}/{len(tracks)}곡이 분류됨[/dim]")

    if dry_run:
        console.print("[yellow]--dry-run: Spotify에 생성하지 않음[/yellow]")
        return

    if not Confirm.ask(f"\n위 {len(categories)}개 플리를 Spotify에 생성할까요?", default=True):
        return

    lib = _load_library(ctx.obj["library_path"])
    created: list[tuple[str, str]] = []  # (이름, URL)
    for cat in categories:
        name = f"{prefix}{cat.name}"
        console.print(f"생성 중: {name} ({len(cat.track_uris)}곡)...")
        pl = sp.create_playlist(
            name=name,
            track_uris=cat.track_uris,
            description=f"auto: {cat.description}"[:300],
            public=public,
        )
        url = pl.get("external_urls", {}).get("spotify", pl["id"])
        created.append((name, url))
        lib.upsert_playlist(
            PlaylistRecord(
                name=name,
                spotify_id=pl["id"],
                criteria={
                    "auto": True,
                    "style": style_hint,
                    "category": cat.name,
                    "description": cat.description,
                },
            )
        )
    lib.save()

    console.print(f"\n[green]{len(created)}개 플리 생성 완료[/green]")
    for name, url in created:
        console.print(f"  • {name}: {url}")


@cli.group()
def playlist() -> None:
    """플레이리스트 생성·동기화."""


@playlist.command("create")
@click.argument("name")
@click.option("--tag", "tags", multiple=True)
@click.option("--any-tag", "any_tags", multiple=True)
@click.option("--min-rating", type=click.IntRange(0, 5), default=None)
@click.option("--ai", "ai_count", type=int, default=0, help="Claude로 추가 추천할 곡 수")
@click.option("--mood", default="", help="AI 추천에 사용할 분위기")
@click.option("--public", is_flag=True, help="공개 플레이리스트로 생성")
@click.option("--limit", type=int, default=100, help="최대 트랙 수")
@click.pass_context
def playlist_create(
    ctx: click.Context,
    name: str,
    tags: tuple[str, ...],
    any_tags: tuple[str, ...],
    min_rating: Optional[int],
    ai_count: int,
    mood: str,
    public: bool,
    limit: int,
) -> None:
    """기준대로 큐레이션하고 Spotify에 새 플레이리스트를 생성."""
    from .spotify_client import SpotifyClient

    lib = _load_library(ctx.obj["library_path"])
    curated, uris = _curate(lib, tags, any_tags, min_rating, ai_count, mood, limit)

    if not uris:
        console.print("[red]선별된 곡이 없습니다[/red]")
        return

    console.print(f"\n선별 결과 {len(uris)}곡:")
    for t in curated[:20]:
        console.print(f"  • {t.display}")
    if len(curated) > 20:
        console.print(f"  ... 외 {len(curated) - 20}곡")

    if not Confirm.ask(f"\n'{name}' 이름으로 Spotify 플레이리스트를 생성할까요?", default=True):
        return

    sp = SpotifyClient()
    pl = sp.create_playlist(
        name=name,
        track_uris=uris,
        description=f"playlist-builder: tags={list(tags)} ai={ai_count}",
        public=public,
    )

    lib.upsert_playlist(
        PlaylistRecord(
            name=name,
            spotify_id=pl["id"],
            criteria={
                "tags": list(tags),
                "any_tags": list(any_tags),
                "min_rating": min_rating,
                "ai_count": ai_count,
                "mood": mood,
                "limit": limit,
            },
        )
    )
    lib.save()
    console.print(f"[green]생성 완료[/green]: {pl.get('external_urls', {}).get('spotify', pl['id'])}")


@playlist.command("sync")
@click.argument("name")
@click.pass_context
def playlist_sync(ctx: click.Context, name: str) -> None:
    """저장된 criteria로 다시 큐레이션해 기존 플레이리스트를 덮어쓴다."""
    from .spotify_client import SpotifyClient

    lib = _load_library(ctx.obj["library_path"])
    record = lib.playlists.get(name)
    if record is None or not record.spotify_id:
        console.print(f"[red]'{name}' 플레이리스트 정보가 없습니다. 먼저 create 해주세요[/red]")
        return

    c = record.criteria or {}
    curated, uris = _curate(
        lib,
        tuple(c.get("tags") or ()),
        tuple(c.get("any_tags") or ()),
        c.get("min_rating"),
        int(c.get("ai_count") or 0),
        c.get("mood") or "",
        int(c.get("limit") or 100),
    )

    if not uris:
        console.print("[yellow]선별된 곡이 없습니다. 변경 안 함[/yellow]")
        return

    sp = SpotifyClient()
    sp.replace_playlist_tracks(record.spotify_id, uris)
    lib.upsert_playlist(record)
    lib.save()
    console.print(f"[green]{name} {len(uris)}곡으로 갱신[/green]")


def _curate(
    lib: Library,
    tags: tuple[str, ...],
    any_tags: tuple[str, ...],
    min_rating: Optional[int],
    ai_count: int,
    mood: str,
    limit: int,
) -> tuple[list[Track], list[str]]:
    pool = list(lib.tracks.values())
    if tags:
        pool = filter_tracks(pool, tags=tags, match_all_tags=True)
    if any_tags:
        pool = filter_tracks(pool, tags=any_tags, match_all_tags=False)
    if min_rating is not None:
        pool = filter_tracks(pool, min_rating=min_rating)
    pool = sort_for_playlist(pool)

    ai_tracks: list[Track] = []
    if ai_count > 0:
        from .claude_client import ClaudeClient
        from .spotify_client import SpotifyClient

        seeds = pool[:15]
        if seeds:
            console.print(f"Claude로 추가 {ai_count}곡 추천 중...")
            recs = ClaudeClient().recommend(seeds=seeds, n=ai_count, mood=mood)
            sp = SpotifyClient()
            for r in recs:
                match = sp.search_track(r.search_query())
                if match and match.uri not in {t.uri for t in pool}:
                    ai_tracks.append(match)

    combined = dedupe_by_uri(pool + ai_tracks)[:limit]
    return combined, [t.uri for t in combined]


def _print_track_row(track: Track) -> None:
    console.print(
        f"  {track.display} | ⭐{track.rating if track.rating is not None else '-'} | "
        f"태그: {', '.join(track.tags) or '(없음)'}"
    )


if __name__ == "__main__":
    cli()
