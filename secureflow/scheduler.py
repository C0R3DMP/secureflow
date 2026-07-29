"""Scheduled assessment manager — persistent cron jobs backed by SQLite."""

import logging
from pathlib import Path
from typing import Any, Dict, List

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from secureflow.security import validate_target

logger = logging.getLogger(__name__)

_SCHEDULES_DB = str(Path.home() / ".secureflow" / "schedules.db")
_JOBSTORE_URL = f"sqlite:///{_SCHEDULES_DB}"


def _run_scheduled_scan(target: str) -> None:
    """Execute a security scan — called by APScheduler in a background thread."""
    try:
        from secureflow.crew.orchestrator import CrewOrchestrator
        logger.info(f"[scheduler] Starting scheduled scan: {target}")
        CrewOrchestrator().run_security_crew(target)
        logger.info(f"[scheduler] Scheduled scan complete: {target}")
    except Exception as exc:
        logger.error(f"[scheduler] Scheduled scan failed for {target}: {exc}")


def _parse_cron(expr: str) -> CronTrigger:
    """Parse a 5-field cron expression. Raises ValueError on bad input."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron expression {expr!r}: expected 5 fields "
            "(minute hour day month day_of_week)"
        )
    minute, hour, day, month, day_of_week = parts
    try:
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
    except Exception as exc:
        raise ValueError(f"Invalid cron expression {expr!r}: {exc}") from exc


class ScheduleManager:
    """CRUD interface for persistent scheduled scans."""

    def __init__(self, db_url: str = _JOBSTORE_URL):
        Path(db_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
        jobstores = {"default": SQLAlchemyJobStore(url=db_url)}
        self._scheduler = BackgroundScheduler(jobstores=jobstores, timezone="UTC")
        self._scheduler.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, target: str, cron: str) -> str:
        """
        Schedule a recurring scan.

        Args:
            target: Hostname / IP to scan.
            cron:   5-field cron expression, e.g. "0 3 * * *".

        Returns:
            Job ID string.

        Raises:
            ValueError: If the cron expression or the target is invalid.
        """
        # Validate before persisting: a bad target would otherwise sit in the
        # job store and fail on every future firing.
        target = validate_target(target)
        trigger = _parse_cron(cron)
        job = self._scheduler.add_job(
            _run_scheduled_scan,
            trigger=trigger,
            args=[target],
            id=None,           # auto-generate
            name=f"scan:{target}",
            replace_existing=False,
            misfire_grace_time=300,
        )
        logger.info(f"Scheduled scan added: {job.id} → {target} @ {cron}")
        return job.id

    def remove(self, job_id: str) -> None:
        """Remove a scheduled scan by job ID. Raises KeyError if not found."""
        job = self._scheduler.get_job(job_id)
        if job is None:
            raise KeyError(f"No scheduled scan with id {job_id!r}")
        self._scheduler.remove_job(job_id)
        logger.info(f"Scheduled scan removed: {job_id}")

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return all scheduled jobs as a list of dicts."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append({
                "id": job.id,
                "name": job.name,
                "target": job.args[0] if job.args else "",
                "trigger": str(job.trigger),
                "next_run": next_run,
            })
        return jobs

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)


# Module-level singleton — shared across CLI + server in the same process
_manager: ScheduleManager = None


def get_manager() -> ScheduleManager:
    """Return the process-wide ScheduleManager, creating it on first call."""
    global _manager
    if _manager is None:
        _manager = ScheduleManager()
    return _manager
