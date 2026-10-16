"""Explicit fictional hardware profiles, independent of the physical host."""

from godfather_contracts import GPU, Advertisement, ModelInventory, Resources


def profile(name: str) -> Advertisement:
    common = Resources(
        source="simulated",
        cpu_name="SIMULATED CPU",
        cpu_count=8,
        ram_bytes=32 * 1024**3,
        available_ram_bytes=24 * 1024**3,
        cpu_percent=5,
    )
    advertisement = Advertisement(
        os="windows",
        os_version="SIMULATED Windows 11",
        architecture="x86_64",
        resources=common,
        primary_capabilities=["coding"],
        secondary_capabilities=["research"],
        scheduling_policy="preferred",
        runtimes=["python"],
        discovery_warnings=["SIMULATED-HARDWARE-NOT-PHYSICAL-TELEMETRY"],
    )
    if name == "LV-01":
        common.gpus = [
            GPU(
                name="SIMULATED NVIDIA GPU",
                backend="cuda",
                evidence="simulated",
                memory_bytes=12 * 1024**3,
                memory_used_bytes=0,
                utilization_percent=0,
            )
        ]
    elif name == "LV-02":
        common.cpu_count = 16
        common.ram_bytes = 64 * 1024**3
        common.gpus = [
            GPU(
                name="SIMULATED AMD GPU",
                backend="rocm",
                evidence="simulated",
                memory_bytes=16 * 1024**3,
                memory_used_bytes=0,
            )
        ]
        advertisement.primary_capabilities = ["images"]
        advertisement.secondary_capabilities = ["coding"]
        advertisement.concurrency_limit = 2
        advertisement.scheduling_policy = "dedicated"
    elif name in ("LA-01", "LA-02"):
        advertisement.os = "macos"
        advertisement.os_version = "SIMULATED macOS"
        advertisement.architecture = "arm64" if name == "LA-01" else "x86_64"
        advertisement.primary_capabilities = ["analytics", "reports"]
        advertisement.secondary_capabilities = ["coding"]
        advertisement.scheduling_policy = "shared"
        if name == "LA-01":
            common.gpus = [
                GPU(
                    name="SIMULATED Apple GPU",
                    backend="metal",
                    evidence="simulated",
                    unified_memory=True,
                )
            ]
    else:
        raise ValueError("Choose LV-01, LV-02, LA-01 or LA-02")
    advertisement.installed_models = [ModelInventory(runtime="simulated", identifier="demo-only")]
    return advertisement
