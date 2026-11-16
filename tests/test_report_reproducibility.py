"""Report bytes must not depend on wall-clock date or elapsed run time."""
from dataclasses import replace
import pytest
import main
from scripts import run_top_real_fleet as real, run_controlled_reports as controlled


@pytest.fixture
def top_run():
    return real.run_scenario(real.select_scenarios()[0])


def test_main_report_ignores_clock_and_duration_in_reproducible_mode(top_run):
    a=main.render_markdown([top_run],'2026-01-01',reproducible=True)
    b=main.render_markdown([replace(top_run,elapsed=999)],'2099-12-31',reproducible=True)
    assert a==b
    assert '999' not in b and '2099-12-31' not in b


def test_default_report_writer_is_reproducible(top_run,tmp_path):
    path=tmp_path/'report.md'
    a=main.write_markdown([top_run],path)
    b=main.write_markdown([replace(top_run,elapsed=999)],path)
    assert a==b==path.read_text(encoding='utf-8')
    assert path.read_bytes()==a.encode('utf-8')


def test_top_report_is_reproducible(top_run):
    a=real.render_markdown([top_run],'2026-01-01',reproducible=True)
    b=real.render_markdown([replace(top_run,elapsed=999)],'2099-12-31',reproducible=True)
    assert a==b


@pytest.mark.parametrize('config',controlled.CONFIGS.values())
def test_controlled_reports_are_reproducible(config):
    assert controlled.render_report(config,[],'2026-01-01',reproducible=True)==controlled.render_report(config,[],'2099-12-31',reproducible=True)
