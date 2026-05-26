"""Tests for M11: ScheduleManager — cron jobs backed by SQLite."""

import pytest
import tempfile


def _manager(tmp_dir):
    from secureflow.scheduler import ScheduleManager
    db_url = f"sqlite:///{tmp_dir}/schedules.db"
    return ScheduleManager(db_url=db_url)


class TestScheduleManager:

    def test_add_returns_job_id(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            job_id = mgr.add("scanme.nmap.org", "0 3 * * *")
            assert isinstance(job_id, str)
            assert len(job_id) > 0
        finally:
            mgr.shutdown()

    def test_add_job_appears_in_list(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            job_id = mgr.add("192.168.1.1", "*/30 * * * *")
            jobs = mgr.list_jobs()
            ids = [j["id"] for j in jobs]
            assert job_id in ids
        finally:
            mgr.shutdown()

    def test_list_contains_target(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            mgr.add("target.example.com", "0 0 * * *")
            jobs = mgr.list_jobs()
            targets = [j["target"] for j in jobs]
            assert "target.example.com" in targets
        finally:
            mgr.shutdown()

    def test_list_contains_next_run(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            mgr.add("host.local", "0 12 * * *")
            jobs = mgr.list_jobs()
            assert jobs[0]["next_run"] is not None
        finally:
            mgr.shutdown()

    def test_remove_deletes_job(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            job_id = mgr.add("remove.me", "0 6 * * *")
            mgr.remove(job_id)
            ids = [j["id"] for j in mgr.list_jobs()]
            assert job_id not in ids
        finally:
            mgr.shutdown()

    def test_remove_nonexistent_raises_key_error(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            with pytest.raises(KeyError):
                mgr.remove("nonexistent-id-xyz")
        finally:
            mgr.shutdown()

    def test_multiple_jobs_coexist(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            id1 = mgr.add("host1.local", "0 1 * * *")
            id2 = mgr.add("host2.local", "0 2 * * *")
            jobs = mgr.list_jobs()
            ids = [j["id"] for j in jobs]
            assert id1 in ids
            assert id2 in ids
        finally:
            mgr.shutdown()

    def test_empty_list_before_any_add(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            assert mgr.list_jobs() == []
        finally:
            mgr.shutdown()


class TestCronValidation:

    def test_valid_cron_accepted(self, tmp_path):
        mgr = _manager(tmp_path)
        try:
            valid_exprs = [
                "0 3 * * *",
                "*/15 * * * *",
                "0 0 1 * *",
                "30 8 * * 1",
            ]
            for expr in valid_exprs:
                job_id = mgr.add("test.host", expr)
                mgr.remove(job_id)
        finally:
            mgr.shutdown()

    def test_wrong_field_count_raises(self):
        from secureflow.scheduler import _parse_cron
        with pytest.raises(ValueError, match="5 fields"):
            _parse_cron("0 3 * *")     # only 4 fields

    def test_six_field_cron_raises(self):
        from secureflow.scheduler import _parse_cron
        with pytest.raises(ValueError, match="5 fields"):
            _parse_cron("0 0 3 * * *")  # 6 fields (seconds-style)

    def test_empty_expression_raises(self):
        from secureflow.scheduler import _parse_cron
        with pytest.raises(ValueError):
            _parse_cron("")

    def test_invalid_value_raises(self):
        from secureflow.scheduler import _parse_cron
        with pytest.raises(ValueError):
            _parse_cron("99 99 99 99 99")


class TestCLISchedule:

    def test_schedule_group_exists(self):
        from click.testing import CliRunner
        from secureflow.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_schedule_add_help(self):
        from click.testing import CliRunner
        from secureflow.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "add", "--help"])
        assert "--cron" in result.output

    def test_schedule_add_invalid_cron_exits_nonzero(self):
        from click.testing import CliRunner
        from secureflow.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "add", "host.local", "--cron", "bad cron"])
        assert result.exit_code != 0
