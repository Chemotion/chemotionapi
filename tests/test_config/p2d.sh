#!/usr/bin/env bash
# Build and test against an unreleased ELN: any branch, tag or commit of chemotion_ELN (M0.3).
#
# The ELN repo ships a Push2Deploy build (Dockerfile.p2d + docker-compose.p2d.yml) that turns the
# checked-out commit into an image on top of the released one. This script builds that image and
# runs this repo's test stack with it, under its own compose project and volumes (suffix `p2d`), so
# the pinned v4 stack in images.env is never touched.
#
#   p2d.sh build <ref>     shallow-clone <ref>, build chemotion-eln-p2d:<ref>-<sha>, tag :<ref>
#   p2d.sh test  <ref> [pytest args...]
#                          reset the p2d stack from the seed and run the suite (default: all tests)
#   p2d.sh down            stop the p2d stack (volumes are kept)
#   p2d.sh image <ref>     print the image tag that `test` would use
#
# Notes:
# - The first build takes ~45 min (it reinstalls Ruby, Node and all gems); later builds of other
#   refs reuse most layers from the BuildKit cache.
# - The build downloads Ketcher from GitHub near the end; a network timeout there is not a code
#   problem, rerun and the cached layers make it quick.
# - The p2d stack publishes the same host ports as the default one (3579, 54320). Stop whatever
#   holds them first; `test` refuses to start if another container has 3579.
#
# Environment: P2D_REMOTE (default ComPlat/chemotion_ELN on GitHub), P2D_DIR (clone scratch
# space, default ~/.cache/chemotion-p2d).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
REMOTE="${P2D_REMOTE:-https://github.com/ComPlat/chemotion_ELN.git}"
P2D_DIR="${P2D_DIR:-${HOME}/.cache/chemotion-p2d}"
IMAGE_REPO="chemotion-eln-p2d"
SUFFIX="p2d"

die() { echo "p2d: $*" >&2; exit 1; }

# Docker tags allow [A-Za-z0-9_.-]; branch names like feature/x become feature-x.
tag_of() { printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '-' | cut -c1-100; }

image_of() {
    local ref="$1"
    local image="${IMAGE_REPO}:$(tag_of "$ref")"
    docker image inspect "$image" >/dev/null 2>&1 || die "no image ${image}; run: p2d.sh build ${ref}"
    echo "$image"
}

cmd_build() {
    local ref="${1:?usage: p2d.sh build <branch|tag|commit>}"
    mkdir -p "$P2D_DIR"
    # Global, not local: the EXIT trap runs after this function has returned.
    P2D_WORK="$(mktemp -d "${P2D_DIR}/build.XXXXXX")"
    trap 'rm -rf -- "${P2D_WORK:?}"' EXIT
    local work="$P2D_WORK"

    # Dockerfile.p2d reads the commit to check out from .git/shallow, which only a shallow clone
    # has, and which must hold exactly one commit.
    echo "p2d: cloning ${ref} from ${REMOTE}"
    if ! git clone -q --depth 1 --branch "$ref" "$REMOTE" "${work}/eln" 2>/dev/null; then
        # Not a branch or tag: treat it as a commit.
        git init -q "${work}/eln"
        git -C "${work}/eln" remote add origin "$REMOTE"
        git -C "${work}/eln" fetch -q --depth 1 origin "$ref" || die "cannot fetch ${ref} from ${REMOTE}"
        git -C "${work}/eln" checkout -q FETCH_HEAD
    fi
    [ -f "${work}/eln/Dockerfile.p2d" ] || die "${ref} has no Dockerfile.p2d (it exists from ELN v3.1.0-rc on)"
    [ "$(wc -l < "${work}/eln/.git/shallow")" -eq 1 ] || die "expected one commit in .git/shallow"

    local sha tag
    sha="$(git -C "${work}/eln" rev-parse --short HEAD)"
    tag="$(tag_of "$ref")"
    echo "p2d: building ${IMAGE_REPO}:${tag}-${sha} (first build ~45 min)"
    DOCKER_BUILDKIT=1 docker build --progress=plain \
        --build-arg "REMOTE=${REMOTE}" \
        -f "${work}/eln/Dockerfile.p2d" \
        -t "${IMAGE_REPO}:${tag}-${sha}" -t "${IMAGE_REPO}:${tag}" \
        "${work}/eln"
    echo "p2d: built ${IMAGE_REPO}:${tag}-${sha}, also tagged ${IMAGE_REPO}:${tag}"
}

cmd_test() {
    local ref="${1:?usage: p2d.sh test <ref> [pytest args...]}"
    shift
    local image
    image="$(image_of "$ref")"

    local holder
    holder="$(docker ps --filter publish=3579 --format '{{.Names}}' | grep -v "^chemotion-test-${SUFFIX}-" || true)"
    [ -z "$holder" ] || die "port 3579 is held by: ${holder//$'\n'/, }. Stop that stack first."

    [ "$#" -gt 0 ] || set -- -m "" -q
    echo "p2d: testing against ${image}"
    cd "${REPO_ROOT}/tests"
    CHEMOTION_ELN_IMAGE="$image" CHEMOTION_STACK_SUFFIX="$SUFFIX" NO_SETUP=0 uv run pytest "$@"
}

cmd_down() {
    # compose.yml requires all three variables even to stop; the image doesn't matter here.
    CHEMOTION_STACK_SUFFIX="$SUFFIX" CHEMOTION_ELN_IMAGE="${IMAGE_REPO}:unused" \
        docker compose --env-file "${HERE}/images.env" -f "${HERE}/compose.yml" down
}

case "${1:-}" in
    build) shift; cmd_build "$@" ;;
    test)  shift; cmd_test "$@" ;;
    down)  shift; cmd_down "$@" ;;
    image) shift; image_of "${1:?usage: p2d.sh image <ref>}" ;;
    *) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
