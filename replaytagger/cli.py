from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import click
import structlog

if TYPE_CHECKING:
    from replaytagger.notifications import NotificationClient
    from replaytagger.plex_client import PlexClient
    from replaytagger.youtube_client import YouTubeClient

from replaytagger import __version__
from replaytagger import logging as rt_logging
from replaytagger.config import AppConfig, load_config
from replaytagger.db import StateDB
from replaytagger.tagger import Tagger, compute_content_hash

log = structlog.get_logger(__name__)


def _validate_config(config: AppConfig) -> None:
    errors = []

    if config.plex.enabled and not config.plex.token:
        log.warning(
            "plex_token_missing",
            reason=(
                "plex.enabled is true but no token found;"
                " set PLEX_TOKEN in .env (Plex Web → any item → (...) → Get Info → View XML)"
            ),
        )

    if config.youtube.enabled:
        if config.youtube.privacy not in ("private", "unlisted", "public"):
            errors.append(
                f"youtube.privacy must be private, unlisted, or public"
                f" (got '{config.youtube.privacy}')"
            )
        if config.youtube.upload_after_days < 0:
            errors.append("youtube.upload_after_days must be 0 or greater")
        has_env_creds = bool(
            os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_CLIENT_SECRET")
        )
        creds_file_missing = not config.youtube.credentials_file.exists()
        if config.youtube.auto_upload and not has_env_creds and creds_file_missing:
            errors.append(
                f"YouTube credentials not found: set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET"
                f" env vars, or provide credentials_file: {config.youtube.credentials_file}"
            )

    if config.debounce_seconds <= 0:
        errors.append("debounce_seconds must be greater than 0")

    if errors:
        for error in errors:
            log.error("config_error", reason=error)
        sys.exit(1)


def _resolve_game(folder_name: str, mapping: dict[str, str]) -> str:
    return mapping.get(folder_name, folder_name)


def _build_plex(config: AppConfig):  # type: ignore[no-untyped-def]
    if not config.plex.enabled:
        return None
    if not config.plex.token:
        log.warning("plex_disabled", reason="PLEX_TOKEN not set")
        return None
    from replaytagger.plex_client import PlexClient

    try:
        client = PlexClient(
            config.plex.url, config.plex.token, config.plex.library_name, config.plex.verify_ssl
        )
        client.list_collections()  # validate library name exists at startup
        return client
    except ValueError as exc:
        log.error(
            "plex_library_not_found",
            reason=str(exc),
            hint="Check library_name in config.yaml matches your Plex library exactly",
        )
        sys.exit(1)
    except Exception:
        log.warning(
            "plex_degraded",
            reason="connection failed; tagging will continue without Plex integration",
        )
        return None


def _build_notifications(config: AppConfig):  # type: ignore[no-untyped-def]
    if not config.notifications.webhooks:
        return None
    from replaytagger.notifications import NotificationClient

    return NotificationClient(config.notifications.webhooks)


def _build_youtube(config: AppConfig):  # type: ignore[no-untyped-def]
    if not config.youtube.enabled:
        return None
    from replaytagger.youtube_client import YouTubeClient

    client = YouTubeClient(config.youtube.credentials_file, config.youtube.token_file)
    client.authenticate()
    return client


def _upload_file(
    file_path: Path,
    game_name: str,
    content_hash: str | None,
    config: AppConfig,
    youtube: YouTubeClient,
    db: StateDB,
    notifier: NotificationClient | None,
) -> None:
    bound = log.bind(file=file_path.name, game=game_name)
    if content_hash and db.get_youtube_id_by_hash(content_hash) is not None:
        bound.debug("skipped_upload", reason="already_uploaded")
        return
    if db.get_youtube_id(file_path) is not None:
        bound.debug("skipped_upload", reason="already_uploaded")
        return
    first_seen = db.get_first_seen(file_path)
    if first_seen is not None:
        age_days = (datetime.now(UTC) - first_seen).days
        if age_days < config.youtube.upload_after_days:
            bound.debug(
                "upload_deferred",
                age_days=age_days,
                required=config.youtube.upload_after_days,
            )
            return
    try:
        video_id = youtube.upload(file_path, game_name, privacy=config.youtube.privacy)
        db.mark_uploaded(file_path, video_id)
        if notifier:
            from replaytagger.notifications import NotifyEvent

            notifier.notify(
                NotifyEvent.CLIP_UPLOADED,
                game=game_name,
                file=file_path.name,
                video_id=video_id,
            )
    except Exception as exc:
        bound.error("upload_failed", error=str(exc))


def _process_file(
    file_path: Path,
    config: AppConfig,
    tagger: Tagger,
    db: StateDB,
    plex: PlexClient | None,
    youtube: YouTubeClient | None,
    dry_run: bool,
    notifier: NotificationClient | None = None,
    force: bool = False,
) -> bool:
    game_name = _resolve_game(file_path.parent.name, config.game_name_map)
    bound = log.bind(file=file_path.name, game=game_name)

    if not force and db.is_tagged(file_path):
        bound.debug("skipped", reason="already_tagged")
        return False

    tagged = tagger.tag(file_path, game_name, dry_run=dry_run, force=force)

    if not tagged and not dry_run and tagger.get_genre(file_path) == game_name:
        # Genre was written in a prior run but not recorded in DB; backfill it
        tagged = True

    content_hash = compute_content_hash(file_path) if not dry_run else None

    if tagged and not dry_run:
        db.mark_tagged(file_path, game_name, content_hash)

    if youtube and config.youtube.auto_upload and not dry_run:
        _upload_file(file_path, game_name, content_hash, config, youtube, db, notifier)

    return tagged


@click.group()
@click.version_option(__version__)
@click.option(
    "--config",
    "config_path",
    default="config.yaml",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to config.yaml",
)
@click.option("--dry-run", is_flag=True, help="Preview changes without modifying files")
@click.pass_context
def main(ctx: click.Context, config_path: Path, dry_run: bool) -> None:
    """ReplayTagger: tag game clips by genre so Plex builds per-game collections."""
    ctx.ensure_object(dict)
    cfg = load_config(config_path)
    rt_logging.configure(cfg.logging.level, cfg.logging.format)
    # Auth commands obtain credentials; skip validation so they can run before
    # a token exists even when plex.enabled or youtube.enabled is already set.
    if ctx.invoked_subcommand not in ("plex-auth", "youtube-auth", "doctor", "retag"):
        _validate_config(cfg)
    ctx.obj["config"] = cfg
    ctx.obj["dry_run"] = dry_run


@main.command()
@click.option("--force", is_flag=True, help="Retag all clips even if already tagged")
@click.pass_context
def run(ctx: click.Context, force: bool) -> None:
    """Scan all clips once, tag untagged files, then exit."""
    config: AppConfig = ctx.obj["config"]
    dry_run: bool = ctx.obj["dry_run"]

    db = StateDB(config.data_dir / "state.db")
    tagger = Tagger(config.ffmpeg_path, config.ffprobe_path)
    plex = _build_plex(config)
    youtube = _build_youtube(config)
    notifier = _build_notifications(config)

    if not config.clips_dir.exists():
        log.error("clips_dir_not_found", path=str(config.clips_dir))
        sys.exit(1)

    clips = [
        f
        for f in config.clips_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in config.extensions
    ]

    log.info("scan_started", total=len(clips), dry_run=dry_run, force=force)

    newly_tagged = 0
    for clip in clips:
        try:
            if _process_file(
                clip, config, tagger, db, plex, youtube, dry_run, notifier, force=force
            ):
                newly_tagged += 1
        except Exception as exc:
            log.error("file_error", file=clip.name, error=str(exc))
            if notifier:
                from replaytagger.notifications import NotifyEvent

                notifier.notify(NotifyEvent.ERROR, file=clip.name, error=str(exc))

    # Ensure collections exist for every game in the clips directory
    if plex and config.plex.auto_create_collections:
        for game in {_resolve_game(f.parent.name, config.game_name_map) for f in clips}:
            plex.ensure_collection(game)

    # Trigger a single Plex scan after all files are processed
    if plex and config.plex.auto_scan:
        plex.scan()

    stats = db.stats()
    log.info("scan_complete", **stats)

    if notifier and not dry_run and newly_tagged > 0:
        from replaytagger.notifications import NotifyEvent

        notifier.notify(NotifyEvent.SCAN_COMPLETE, tagged=newly_tagged, total=len(clips))


@main.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Watch for new clips and process them as they arrive (runs forever)."""
    from replaytagger.watcher import watch as watch_clips

    config: AppConfig = ctx.obj["config"]
    dry_run: bool = ctx.obj["dry_run"]

    db = StateDB(config.data_dir / "state.db")
    tagger = Tagger(config.ffmpeg_path, config.ffprobe_path)
    plex = _build_plex(config)
    youtube = _build_youtube(config)
    notifier = _build_notifications(config)

    if not config.clips_dir.exists():
        log.error("clips_dir_not_found", path=str(config.clips_dir))
        sys.exit(1)

    # Process existing untagged files before entering watch mode
    log.info("processing_existing_clips")
    ctx.invoke(run, force=False)

    if dry_run:
        log.info("dry_run_complete", message="watch loop skipped in dry-run mode")
        return

    def on_new_clip(file_path: Path) -> None:
        try:
            newly = _process_file(file_path, config, tagger, db, plex, youtube, dry_run, notifier)
            if plex and config.plex.auto_scan:
                plex.scan()
            if notifier and newly and not dry_run:
                from replaytagger.notifications import NotifyEvent

                notifier.notify(
                    NotifyEvent.CLIP_TAGGED,
                    game=_resolve_game(file_path.parent.name, config.game_name_map),
                    file=file_path.name,
                )
        except Exception as exc:
            log.error("watch_file_error", file=file_path.name, error=str(exc))
            if notifier:
                from replaytagger.notifications import NotifyEvent

                notifier.notify(NotifyEvent.ERROR, file=file_path.name, error=str(exc))

    watch_clips(
        config.clips_dir,
        on_new_clip,
        config.extensions,
        config.debounce_seconds,
        heartbeat_path=config.data_dir / ".health",
    )


@main.command("plex-auth")
@click.pass_context
def plex_auth(ctx: click.Context) -> None:
    """Run the Plex PIN OAuth flow to get a permanent auth token."""
    config: AppConfig = ctx.obj["config"]
    from replaytagger.plex_auth import authenticate

    token = authenticate(config.data_dir)
    token_file = config.data_dir / "plex_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token)
    click.echo("\nAuthorization successful!")
    click.echo(f"Token saved to {token_file}; no environment variable needed.")
    click.echo(f"To set it as an env var instead:\n\n  PLEX_TOKEN={token}\n")


@main.command("youtube-auth")
@click.pass_context
def youtube_auth(ctx: click.Context) -> None:
    """Run the YouTube OAuth2 flow to authorize uploads."""
    config: AppConfig = ctx.obj["config"]
    from replaytagger.youtube_client import YouTubeClient

    client = YouTubeClient(config.youtube.credentials_file, config.youtube.token_file)
    client.authenticate()
    click.echo("YouTube authentication successful. Token saved.")


@main.command("youtube-sync")
@click.pass_context
def youtube_sync(ctx: click.Context) -> None:
    """Upload all tagged clips that have passed the upload_after_days threshold."""
    config: AppConfig = ctx.obj["config"]
    dry_run: bool = ctx.obj["dry_run"]

    if not config.youtube.enabled:
        click.echo("YouTube is not enabled. Set youtube.enabled: true in config.yaml.")
        return

    from replaytagger.youtube_client import YouTubeClient

    client = YouTubeClient(config.youtube.credentials_file, config.youtube.token_file)
    client.authenticate()

    db = StateDB(config.data_dir / "state.db")

    if not config.clips_dir.exists():
        log.error("clips_dir_not_found", path=str(config.clips_dir))
        sys.exit(1)

    clips = [
        f
        for f in config.clips_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in config.extensions
    ]

    uploaded = skipped = 0

    for clip in clips:
        bound = log.bind(file=clip.name, game=clip.parent.name)
        content_hash = compute_content_hash(clip)

        if (
            db.get_youtube_id_by_hash(content_hash) is not None
            or db.get_youtube_id(clip) is not None
        ):
            skipped += 1
            continue

        if db.get_first_seen(clip) is None:
            bound.debug("skipped_sync", reason="not_tagged")
            continue

        if dry_run:
            bound.info("would_upload", file=clip.name)
            continue

        try:
            video_id = client.upload(
                clip,
                clip.parent.name,
                privacy=config.youtube.privacy,
            )
            db.mark_tagged(clip, clip.parent.name, content_hash)
            db.mark_uploaded(clip, video_id)
            uploaded += 1
        except Exception as exc:
            bound.error("upload_failed", error=str(exc))

    log.info("youtube_sync_complete", uploaded=uploaded, skipped=skipped)


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--privacy",
    type=click.Choice(["private", "unlisted", "public"]),
    default=None,
    help="Override privacy setting from config",
)
@click.pass_context
def upload(ctx: click.Context, file: Path, privacy: str | None) -> None:
    """Upload a single clip to YouTube."""
    config: AppConfig = ctx.obj["config"]
    db = StateDB(config.data_dir / "state.db")

    content_hash = compute_content_hash(file)

    if db.get_youtube_id_by_hash(content_hash) is not None:
        click.echo(f"Already uploaded (same content): {file.name}")
        return

    if db.get_youtube_id(file) is not None:
        click.echo(f"Already uploaded: {file.name}")
        return

    from replaytagger.youtube_client import YouTubeClient

    client = YouTubeClient(config.youtube.credentials_file, config.youtube.token_file)
    client.authenticate()

    game_name = file.parent.name
    effective_privacy = privacy or config.youtube.privacy

    video_id = client.upload(
        file,
        game_name,
        privacy=effective_privacy,
    )
    # Ensure row exists with hash so future dedup checks work
    db.mark_tagged(file, game_name, content_hash)
    db.mark_uploaded(file, video_id)
    click.echo(f"Uploaded: https://youtu.be/{video_id}")


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show statistics from the state database."""
    config: AppConfig = ctx.obj["config"]
    db = StateDB(config.data_dir / "state.db")
    stats = db.stats()
    click.echo(f"Tagged clips : {stats['total_tagged']}")
    click.echo(f"YT uploads   : {stats['total_uploaded']}")
    last = db.last_tagged()
    if last:
        name = Path(last["file_path"]).name
        click.echo(f"Last tagged  : {name} ({last['game_name']}) at {last['tagged_at']}")


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--game", "game_name", default=None, help="Game name override (default: folder name)")
@click.pass_context
def retag(ctx: click.Context, file: Path, game_name: str | None) -> None:
    """Force-retag a single clip, overriding any existing genre tag."""
    config: AppConfig = ctx.obj["config"]
    dry_run: bool = ctx.obj["dry_run"]

    resolved_game = game_name or _resolve_game(file.parent.name, config.game_name_map)
    tagger = Tagger(config.ffmpeg_path, config.ffprobe_path)
    db = StateDB(config.data_dir / "state.db")

    tagged = tagger.tag(file, resolved_game, dry_run=dry_run, force=True)

    if dry_run:
        click.echo(f"Would retag: {file.name} -> {resolved_game}")
        return

    if tagged:
        content_hash = compute_content_hash(file)
        db.mark_tagged(file, resolved_game, content_hash)
        click.echo(f"Retagged: {file.name} -> {resolved_game}")
    else:
        click.echo(f"Retag failed: {file.name}", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check configuration, paths, and connectivity."""
    import shutil

    # Silence structlog - doctor uses click.echo for its own formatted output.
    rt_logging.configure("CRITICAL", "json", silent=True)

    config: AppConfig = ctx.obj["config"]
    passed = True
    counts: dict[str, int] = {"OK": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}

    def _line(status: str, label: str, detail: str = "") -> None:
        colors = {"OK": "green", "FAIL": "red", "WARN": "yellow", "SKIP": "bright_black"}
        styled = click.style(f"{status:<4}", fg=colors.get(status, "white"), bold=status == "FAIL")
        click.echo(f"[{styled}] {label}" + (f": {detail}" if detail else ""))
        counts[status] = counts.get(status, 0) + 1

    def ok(label: str, detail: str = "") -> None:
        _line("OK", label, detail)

    def fail(label: str, detail: str = "") -> None:
        nonlocal passed
        passed = False
        _line("FAIL", label, detail)

    def warn(label: str, detail: str = "") -> None:
        _line("WARN", label, detail)

    def skip(label: str, detail: str = "") -> None:
        _line("SKIP", label, detail)

    # Clips directory
    if config.clips_dir.exists():
        clip_count = sum(
            1
            for f in config.clips_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in config.extensions
        )
        ok("clips_dir", f"{config.clips_dir} ({clip_count} clip(s))")
    else:
        fail("clips_dir", f"{config.clips_dir} not found")

    # ffmpeg / ffprobe
    for tool in (config.ffmpeg_path, config.ffprobe_path):
        if shutil.which(tool):
            ok(tool)
        else:
            fail(tool, "not found - install ffmpeg or set ffmpeg_path/ffprobe_path in config.yaml")

    # Data directory writable
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        probe = config.data_dir / ".doctor"
        probe.write_text("ok")
        probe.unlink()
        ok("data_dir", str(config.data_dir))
    except Exception as exc:
        fail("data_dir", str(exc))

    # Plex
    if config.plex.enabled:
        if not config.plex.token:
            fail("plex_token", "not set - add PLEX_TOKEN to .env")
        else:
            ok("plex_token")
            # Check plex_token file permissions if token was loaded from file
            token_file = config.data_dir / "plex_token"
            if token_file.exists():
                mode = token_file.stat().st_mode & 0o777
                if mode & 0o044:  # group-read or other-read
                    warn(
                        "plex_token_perms",
                        f"{token_file} mode {oct(mode)[-3:]} - run: chmod 600 {token_file}",
                    )
                else:
                    ok("plex_token_perms", f"{token_file} permissions ok")
            try:
                from replaytagger.plex_client import PlexClient

                plex = PlexClient(
                    config.plex.url,
                    config.plex.token,
                    config.plex.library_name,
                    config.plex.verify_ssl,
                )
                ok("plex_reachable", config.plex.url)
                plex.list_collections()
                ok("plex_library", config.plex.library_name)
            except ValueError as exc:
                fail("plex_library", str(exc))
            except Exception as exc:
                fail("plex_reachable", str(exc))
    else:
        skip("plex", "not enabled")

    # YouTube
    if config.youtube.enabled:
        has_env = bool(
            os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_CLIENT_SECRET")
        )
        if has_env or config.youtube.credentials_file.exists():
            ok("youtube_credentials")
        else:
            warn(
                "youtube_credentials",
                f"set YOUTUBE_CLIENT_ID/SECRET or provide {config.youtube.credentials_file}",
            )
    else:
        skip("youtube", "not enabled")

    # Game name map
    if config.game_name_map:
        ok("game_name_map", f"{len(config.game_name_map)} mapping(s) active")

    total = counts["OK"] + counts["FAIL"] + counts["WARN"] + counts["SKIP"]
    summary_parts = [f"{counts['OK']} passed"]
    if counts["FAIL"]:
        summary_parts.append(click.style(f"{counts['FAIL']} failed", fg="red", bold=True))
    if counts["WARN"]:
        summary_parts.append(click.style(f"{counts['WARN']} warned", fg="yellow"))
    if counts["SKIP"]:
        summary_parts.append(f"{counts['SKIP']} skipped")
    click.echo(f"\n{', '.join(summary_parts)} ({total} checks)")

    sys.exit(0 if passed else 1)
