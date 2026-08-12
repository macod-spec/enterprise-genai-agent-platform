"""Bounded local load and injected-failure checks for the MCP gateway."""

import asyncio
import json
import statistics
import time
from pathlib import Path

from enterprise_genai_platform.domain import NovaBankRepository
from enterprise_genai_platform.mcp_boundary import CallerContext, build_local_mcp_gateway
from enterprise_genai_platform.mcp_boundary.contracts import CustomerRecord, CustomerRequest
from enterprise_genai_platform.mcp_boundary.gateway import (
    GovernedMCPGateway,
    MCPToolFailure,
    ToolRegistration,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "config/performance-baseline.json"


def caller(index: int) -> CallerContext:
    return CallerContext(
        subject=f"load-client-{index % 10}",
        roles=frozenset({"agent.invoke"}),
        agent="customer",
        request_id=f"load-request-{index}",
    )


async def run_load(total: int = 250) -> float:
    gateway = build_local_mcp_gateway(NovaBankRepository(), rate_limit=1_000)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            gateway.invoke(
                "customer.get_customer",
                {"customer_id": "CUST-1098"},
                caller(index),
            )
            for index in range(total)
        )
    )
    elapsed = time.perf_counter() - started
    if len(results) != total or len(gateway.audit.records) != total:
        raise RuntimeError("load test lost results or audit records")
    return elapsed


async def run_failures(total: int = 25) -> float:
    gateway = GovernedMCPGateway(timeout_seconds=0.005, max_attempts=2, rate_limit=1_000)

    async def unavailable(payload: CustomerRequest, _caller: CallerContext) -> CustomerRecord:
        await asyncio.sleep(0.05)
        raise RuntimeError(payload.customer_id)

    gateway.register(
        ToolRegistration(
            name="customer.unavailable",
            allowed_agents=frozenset({"customer"}),
            required_roles=frozenset({"agent.invoke"}),
            input_model=CustomerRequest,
            output_model=CustomerRecord,
            handler=unavailable,
        )
    )
    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            gateway.invoke(
                "customer.unavailable",
                {"customer_id": "CUST-1098"},
                caller(index),
            )
            for index in range(total)
        ),
        return_exceptions=True,
    )
    elapsed = time.perf_counter() - started
    if not all(isinstance(result, MCPToolFailure) for result in results):
        raise RuntimeError("injected failures did not fail closed")
    if any(
        record.attempt_count != 2 or record.outcome != "timeout" for record in gateway.audit.records
    ):
        raise RuntimeError("timeouts were not bounded and audited")
    return elapsed


async def main() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    requests = int(baseline["requests_per_sample"])
    samples = int(baseline["samples"])
    if requests < 1 or samples < 1:
        raise RuntimeError("performance baseline requests and samples must be positive")

    await run_load(min(25, requests))
    elapsed_samples = [await run_load(requests) for _ in range(samples)]
    throughput_samples = [requests / elapsed for elapsed in elapsed_samples]
    median_throughput = statistics.median(throughput_samples)
    failure_elapsed = await run_failures()
    report = {
        "profile": baseline["profile"],
        "requests_per_sample": requests,
        "samples": samples,
        "elapsed_seconds": [round(value, 4) for value in elapsed_samples],
        "requests_per_second": [round(value, 2) for value in throughput_samples],
        "median_requests_per_second": round(median_throughput, 2),
        "minimum_median_requests_per_second": baseline["minimum_median_requests_per_second"],
        "injected_failures": 25,
        "failure_elapsed_seconds": round(failure_elapsed, 4),
        "maximum_failure_test_seconds": baseline["maximum_failure_test_seconds"],
        "all_failures_bounded": True,
        "baseline_passed": (
            median_throughput >= baseline["minimum_median_requests_per_second"]
            and failure_elapsed <= baseline["maximum_failure_test_seconds"]
        ),
    }
    report_path = ROOT / ".security-reports/load-failure.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["baseline_passed"]:
        raise RuntimeError("local performance or failure-containment baseline was not met")


if __name__ == "__main__":
    asyncio.run(main())
