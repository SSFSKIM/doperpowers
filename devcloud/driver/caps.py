"""The caps (§2): what a session may create without the person. The verdict
is a pure function of the request, the profile's caps and how many
unconfirmed VMs are alive."""

import dataclasses

ASK = "ask the person, then pass --confirmed"


@dataclasses.dataclass(frozen=True)
class Request:
    type: str
    vcpus: int
    type_disk_gb: int
    disk_gb: int | None     # requested (--disk); None: the type's own
    confirmed: bool


@dataclasses.dataclass(frozen=True)
class Verdict:
    line: str               # each cap against the request, for --dry-run
    refusal: str | None     # the first cap the request is over, naming --confirmed


def unconfirmed(vms):
    """The VMs among `vms` (provider Vm dicts) made without the person's yes,
    kept or leased: the ones the count cap counts."""
    return [vm for vm in vms if vm["labels"].get("devcloud") == "vm"
            and vm["labels"].get("devcloud-confirmed") != "1"]


def check(request, caps, alive):
    disk = request.disk_gb or request.type_disk_gb
    added = request.disk_gb is not None and request.disk_gb > request.type_disk_gb
    checks = [
        (f"unconfirmed {alive}/{caps.unconfirmed}", alive >= caps.unconfirmed,
         f"over the count cap ({alive} unconfirmed alive, cap {caps.unconfirmed})"),
        (f"size {request.vcpus}/{caps.vcpu_max} vCPU", request.vcpus > caps.vcpu_max,
         f"{request.type} has {request.vcpus} vCPU, over the size cap ({caps.vcpu_max} vCPU)"),
        (f"disk {disk}/{caps.max_disk_gb} GB", added and disk > caps.max_disk_gb,
         f"{disk} GB is over the disk cap ({caps.max_disk_gb} GB)"),
    ]
    if request.confirmed:
        return Verdict(", ".join(f"{label} {'confirmed' if over else 'ok'}" for label, over, _ in checks), None)
    refusal = next((f"{why}: {ASK}" for _, over, why in checks if over), None)
    return Verdict(", ".join(f"{label} {'over' if over else 'ok'}" for label, over, _ in checks), refusal)
