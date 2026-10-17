# The devcloud container image. Build from the repository root:
#
#   docker build -t devcloud -f devcloud/image/Dockerfile \
#     --build-arg DEVCLOUD_USER=<user> --build-arg DEVCLOUD_UID=<uid> --build-arg DEVCLOUD_HOME=<home> .
#
# Its one build step is image/setup.sh, the same recipe a VM builder runs.
# Run it with the boot descriptor and the seed mounted and --hostname set to
# DEVCLOUD_NAME (devcloud/README.md, "The host"); the entrypoint boots, then
# supervises the host's services in the foreground.
FROM ubuntu:24.04
ARG DEVCLOUD_USER
ARG DEVCLOUD_UID
ARG DEVCLOUD_HOME
RUN --mount=type=bind,source=devcloud,target=/tmp/devcloud bash /tmp/devcloud/image/setup.sh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/bin/sh", "-c", "devcloud-boot && exec devcloud-services"]
