"""The caps (§2): what a session may create without the person. The verdict
is a pure function of the request, the profile's caps and how many
unconfirmed throwaway VMs are alive."""

import dataclasses

from .profile import format_duration

ASK = "ask the person, then pass --confirmed"


@dataclasses.dataclass(frozen=True)
class Request:
    type: str
    vcpus: int
    type_disk_gb: int
    disk_gb: int | None     # requested (--disk); None: the type's own
    lifetime: str           # ttl | keep
    lease: int | None       # seconds, for ttl
    confirmed: bool


@dataclasses.dataclass(frozen=True)
class Verdict:
    line: str               # each cap against the request, for --dry-run
    refusal: str | None     # the first cap the request is over, naming --confirmed


def throwaway(vms):
    """The unconfirmed throwaway VMs among `vms` (provider Vm dicts): the
    ones the throwaway cap counts."""
    return [vm for vm in vms if vm["labels"].get("devcloud") == "vm"
            and vm["labels"].get("devcloud-lifetime") == "ttl"
            and vm["labels"].get("devcloud-confirmed") != "1"]


def check(request, caps, alive):
    disk = request.disk_gb or request.type_disk_gb
    added = request.disk_gb is not None and request.disk_gb > request.type_disk_gb
    checks = []
    if request.lifetime == "ttl":
        checks.append((f"throwaway {alive}/{caps.throwaway}", alive >= caps.throwaway,
                       f"over the throwaway cap ({alive} alive, cap {caps.throwaway})"))
        checks.append((f"lease {format_duration(request.lease)}/{format_duration(caps.lease_max)}",
                       request.lease > caps.lease_max,
                       f"a {format_duration(request.lease)} lease is over the lifetime cap "
                       f"({format_duration(caps.lease_max)})"))
    else:
        checks.append(("lifetime keep", True, "a VM kept without a lease (keep) needs the person's yes"))
    checks.append((f"size {request.vcpus}/{caps.vcpu_max} vCPU", request.vcpus > caps.vcpu_max,
                   f"{request.type} has {request.vcpus} vCPU, over the size cap ({caps.vcpu_max} vCPU)"))
    checks.append((f"disk {disk}/{caps.max_disk_gb} GB", added and disk > caps.max_disk_gb,
                   f"{disk} GB is over the disk cap ({caps.max_disk_gb} GB)"))
    if request.confirmed:
        return Verdict(", ".join(f"{label} {'confirmed' if over else 'ok'}" for label, over, _ in checks), None)
    refusal = next((f"{why}: {ASK}" for _, over, why in checks if over), None)
    return Verdict(", ".join(f"{label} {'over' if over else 'ok'}" for label, over, _ in checks), refusal)
