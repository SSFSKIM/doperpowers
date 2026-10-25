# The devcloud container image. Build from the repository root:
#
#   docker build -t devcloud -f devcloud/image/Dockerfile \
#     --build-arg DEVCLOUD_USER=<user> --build-arg DEVCLOUD_UID=<uid> --build-arg DEVCLOUD_HOME=<home> .
#
# The recipe a VM builder runs as one (image/setup.sh), in layers: the packages
# (image/packages.sh), one layer per part, whose cache key is that file alone,
# so a change anywhere else in devcloud/ reuses them, and a build cache's
# layers are pulled side by side rather than as one stream. The native Claude
# release has its own script-only layer; setup.sh installs from it offline.
# Run it with the boot descriptor and the seed mounted and --hostname set to
# DEVCLOUD_NAME (devcloud/README.md, "The host"); the entrypoint boots, then
# supervises the host's services in the foreground.
FROM ubuntu:24.04
RUN --mount=type=bind,source=devcloud/image/packages.sh,target=/tmp/packages.sh bash /tmp/packages.sh apt
RUN --mount=type=bind,source=devcloud/image/packages.sh,target=/tmp/packages.sh bash /tmp/packages.sh gcloud
RUN --mount=type=bind,source=devcloud/image/packages.sh,target=/tmp/packages.sh bash /tmp/packages.sh tools
RUN --mount=type=bind,source=devcloud/image/packages.sh,target=/tmp/packages.sh bash /tmp/packages.sh chromium
RUN --mount=type=bind,source=devcloud/image/fetch-claude.sh,target=/tmp/fetch-claude.sh bash /tmp/fetch-claude.sh
# The build inputs after the download layers: a RUN after an ARG is keyed on its value.
ARG DEVCLOUD_USER
ARG DEVCLOUD_UID
ARG DEVCLOUD_HOME
RUN --network=none --mount=type=bind,source=devcloud,target=/tmp/devcloud DEVCLOUD_PACKAGES=installed bash /tmp/devcloud/image/setup.sh
STOPSIGNAL SIGTERM
# The services start after a boot that made the host: exit 0, or 3 when only
# step 12 (projects) failed.
ENTRYPOINT ["/bin/sh", "-c", "devcloud-boot; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 3 ] || exit $rc; exec devcloud-services"]
