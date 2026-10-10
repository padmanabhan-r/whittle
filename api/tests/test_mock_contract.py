"""The mock server must obey the contract it exists to demonstrate."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import TypeAdapter

from costcutter.contract import Comparison, Diff, Event, FindingList, Job, PullRequest, SampleList
from costcutter.mock.server import app

EVENTS = TypeAdapter(Event)
SAMPLE = {"source": {"type": "sample", "sample_id": "research-agent-py"}, "monthly_runs": 20000}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as c:
        yield c


async def wait_for(client: httpx.AsyncClient, job_id: str, state: str) -> Job:
    for _ in range(500):
        job = Job.model_validate((await client.get(f"/api/jobs/{job_id}")).json())
        if job.state == state:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job never reached {state}; stuck at {job.state}")


async def start(client: httpx.AsyncClient, body: dict = SAMPLE, **params) -> Job:
    response = await client.post("/api/jobs", json=body, params={"speed": 0, **params})
    assert response.status_code == 201, response.text
    return Job.model_validate(response.json())


async def read_events(client: httpx.AsyncClient, job_id: str, after: int = 0) -> list:
    """Only call once the job is done or failed: the stream stays open until then."""
    text = (await client.get(f"/api/jobs/{job_id}/events", params={"after": after})).text
    lines = [line[6:] for line in text.splitlines() if line.startswith("data: ")]
    return [EVENTS.validate_python(json.loads(line)) for line in lines]


async def run_to_done(client: httpx.AsyncClient, finding_ids: list[str] | None = None) -> Job:
    job = await start(client)
    await wait_for(client, job.id, "awaiting_selection")
    findings = FindingList.model_validate((await client.get(f"/api/jobs/{job.id}/findings")).json())
    ids = finding_ids or [f.id for f in findings.findings]
    response = await client.post(f"/api/jobs/{job.id}/fix", json={"finding_ids": ids})
    assert response.status_code == 202, response.text
    return await wait_for(client, job.id, "done")


@pytest.mark.anyio
async def test_samples(client):
    samples = SampleList.model_validate((await client.get("/api/samples")).json())
    assert {s.language for s in samples.samples} == {"python", "typescript"}


@pytest.mark.anyio
async def test_full_run_is_consistent(client):
    job = await run_to_done(client)
    events = await read_events(client, job.id)

    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[-1].type == "job.done"
    assert job.last_event_seq == len(events)

    states = [e.state for e in events if e.type == "job.state"]
    assert states[:6] == ["cloning", "installing", "baseline", "diagnosing", "awaiting_selection", "fixing"]
    assert all(e.state != e.previous for e in events if e.type == "job.state")

    # The cost meter's last value in each phase is that phase's total.
    for phase, totals in (("baseline", job.summary.baseline), ("after", job.summary.after)):
        calls = [e for e in events if e.type == "llm.call" and e.phase == phase]
        assert len(calls) == totals.llm_calls
        assert calls[-1].running_cost_usd == pytest.approx(totals.cost_usd, abs=1e-5)

    # The smaller model fails the quality check and is the only patch reverted.
    recoveries = [e for e in events if e.type == "recovery"]
    assert [e.action for e in recoveries] == ["reverted"]
    final = {e.finding.id: e.finding for e in events if e.type == "finding"}
    assert sorted(f.status for f in final.values()) == ["applied"] * 4 + ["reverted"]
    reverted = final[recoveries[0].finding_id]
    assert reverted.kind == "oversized_model"

    comparison = Comparison.model_validate((await client.get(f"/api/jobs/{job.id}/comparison")).json())
    assert comparison.after.cost_usd < comparison.baseline.cost_usd
    assert comparison.after.cache_read_tokens > 0 and comparison.baseline.cache_read_tokens == 0
    assert comparison.quality.passed
    assert comparison.saving_pct == job.summary.saving_pct
    assert sum(r.saving_usd_per_run for r in comparison.by_finding) == pytest.approx(
        comparison.saving_usd_per_run, abs=1e-5
    )
    assert comparison.projection.saving_monthly_usd == pytest.approx(
        comparison.saving_usd_per_run * 20000, abs=0.01
    )

    diff = Diff.model_validate((await client.get(f"/api/jobs/{job.id}/diff")).json())
    assert len(diff.files) == 4 and all(f.path.endswith(".py") for f in diff.files)
    patch = await client.get(f"/api/jobs/{job.id}/patch")
    assert patch.text == diff.unified and "attachment" in patch.headers["content-disposition"]
    PullRequest.model_validate((await client.post(f"/api/jobs/{job.id}/pr")).json())


@pytest.mark.anyio
async def test_unselected_findings_are_skipped(client):
    job = await run_to_done(client, ["f1"])
    findings = FindingList.model_validate((await client.get(f"/api/jobs/{job.id}/findings")).json())
    assert [f.status for f in findings.findings] == ["applied", "skipped", "skipped", "skipped", "skipped"]
    assert job.summary.findings_applied == 1


@pytest.mark.anyio
async def test_stream_resumes_after_an_event_id(client):
    job = await run_to_done(client, ["f1"])
    everything = await read_events(client, job.id)
    tail = await read_events(client, job.id, after=len(everything) - 3)
    assert [e.seq for e in tail] == [e.seq for e in everything[-3:]]
    header = await client.get(f"/api/jobs/{job.id}/events", headers={"Last-Event-ID": str(len(everything) - 1)})
    assert header.text.count("data: ") == 1


@pytest.mark.anyio
async def test_failed_job(client):
    job = await start(client, scenario="no_calls")
    job = await wait_for(client, job.id, "failed")
    assert job.error.code == "no_calls_captured"
    events = await read_events(client, job.id)
    assert events[-1].type == "job.error"


@pytest.mark.anyio
async def test_errors_use_one_shape(client):
    cases = [
        (await client.get("/api/jobs/nope"), 404, "job_not_found"),
        (await client.post("/api/jobs", json={"source": {"type": "sample", "sample_id": "x"}}), 404, "sample_not_found"),
        (await client.post("/api/jobs", json={"source": {"type": "github", "repo_url": "https://github.com/a/b"}}), 422, "invalid_request"),
        (await client.post("/api/jobs", json={"source": {"type": "ftp"}}), 422, "invalid_request"),
    ]
    job = await start(client)
    await wait_for(client, job.id, "awaiting_selection")
    cases += [
        (await client.get(f"/api/jobs/{job.id}/comparison"), 409, "job_not_done"),
        (await client.post(f"/api/jobs/{job.id}/fix", json={"finding_ids": ["zz"]}), 422, "unknown_finding"),
    ]
    assert (await client.post(f"/api/jobs/{job.id}/fix", json={"finding_ids": ["f1"]})).status_code == 202
    cases.append((await client.post(f"/api/jobs/{job.id}/fix", json={"finding_ids": ["f1"]}), 409, "not_awaiting_selection"))
    for response, status, code in cases:
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
