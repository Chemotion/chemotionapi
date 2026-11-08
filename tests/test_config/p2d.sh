#!/usr/bin/env bash
# Build and test against an unreleased ELN: any branch, tag or commit of chemotion_ELN (M0.3).
#
# The ELN repo ships a Push2Deploy build (Dockerfile.p2d + docker-compose.p2d.yml) that turns the
# checked-out commit into an image on top of the released one. This script builds that image and
# runs this repo's test stack with it, under its own compose project and volumes (suffix `p2d`), so
# the pinned v4 stack in images.env is never touched.
#
#   p2d.sh build [<ref>]   shallow-clone <ref>, build chemotion-eln-p2d:<ref>-<sha>, tag :<ref>
#   p2d.sh test  [<ref>] [pytest args...]
#                          reset the p2d stack from the seed and run the suite (default: all tests)
#   p2d.sh down            stop the p2d stack (volumes are kept)
#   p2d.sh image [<ref>]   print the image tag that `test` would use
#
# Without <ref> (or when the first `test` argument starts with `-`), the commands use the tested
# ELN recorded in eln-ref.env: ELN_COMMIT if set, else ELN_TAG, else ELN_BRANCH. Whichever of the
# three are empty are looked up on the remote and written back to the file. Without that file
# the default ref is `main`.
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
# space, default ~/.cache/chemotion-p2d), P2D_PIN_FILE (default eln-ref.env next to this script).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
REMOTE="${P2D_REMOTE:-https://github.com/ComPlat/chemotion_ELN.git}"
P2D_DIR="${P2D_DIR:-${HOME}/.cache/chemotion-p2d}"
IMAGE_REPO="chemotion-eln-p2d"
SUFFIX="p2d"
PIN_FILE="${P2D_PIN_FILE:-${HERE}/eln-ref.env}"

die() { echo "p2d: $*" >&2; exit 1; }

# Docker tags allow [A-Za-z0-9_.-]; branch names like feature/x become feature-x.
tag_of() { printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '-' | cut -c1-100; }

image_of() {
    local ref="$1"
    local image="${IMAGE_REPO}:$(tag_of "$ref")"
    docker image inspect "$image" >/dev/null 2>&1 || die "no image ${image}; run: p2d.sh build ${ref}"
    echo "$image"
}

# --- eln-ref.env: the tested ELN -------------------------------------------------------------

# Read KEY's value; the file is parsed, never sourced. Quotes and whitespace are dropped.
pin_get() { sed -n "s/^[[:space:]]*$1=//p" "$PIN_FILE" | tail -n 1 | tr -d "[:space:]\"'"; }

# Set KEY=VALUE in place (portable: no `sed -i`), appending the key if the file lacks it.
pin_set() {
    local key="$1" value="$2" tmp
    tmp="$(mktemp)"
    if grep -q "^[[:space:]]*${key}=" "$PIN_FILE"; then
        sed "s|^[[:space:]]*${key}=.*|${key}=${value}|" "$PIN_FILE" > "$tmp"
    else
        cat "$PIN_FILE" > "$tmp"; echo "${key}=${value}" >> "$tmp"
    fi
    cat "$tmp" > "$PIN_FILE"; rm -f "$tmp"
    echo "p2d: filled in ${key}=${value} in $(basename "$PIN_FILE")" >&2
}

# Fill PIN_BRANCH, PIN_TAG, PIN_COMMIT from the file, resolve the empty ones on the remote and
# write those back. A branch or tag is only filled in when its tip is exactly the commit (ls-remote
# cannot tell which branch merely contains it); otherwise it stays empty.
resolve_pin() {
    PIN_BRANCH="$(pin_get ELN_BRANCH)"
    PIN_TAG="$(pin_get ELN_TAG)"
    PIN_COMMIT="$(pin_get ELN_COMMIT)"
    [ -n "${PIN_BRANCH}${PIN_TAG}${PIN_COMMIT}" ] \
        || die "$(basename "$PIN_FILE") sets none of ELN_BRANCH, ELN_TAG, ELN_COMMIT"
    if [ -n "$PIN_BRANCH" ] && [ -n "$PIN_TAG" ] && [[ "$PIN_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
        return
    fi

    local refs heads tags
    if ! refs="$(git ls-remote --heads --tags "$REMOTE" 2>/dev/null)"; then
        # Offline: a full commit is all a build or test needs; only the fill-in is skipped.
        [[ "$PIN_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "cannot list refs of ${REMOTE}"
        echo "p2d: warning: cannot reach ${REMOTE}; not filling in branch/tag" >&2
        return
    fi
    heads="$(awk '$2 ~ /^refs\/heads\// { n = $2; sub(/^refs\/heads\//, "", n); print $1, n }' <<< "$refs")"
    # "<commit> <tag>": annotated tags point at a tag object, so prefer their peeled ^{} line.
    tags="$(awk '$2 ~ /^refs\/tags\// {
                n = $2; sub(/^refs\/tags\//, "", n)
                if (n ~ /\^\{\}$/) { sub(/\^\{\}$/, "", n); peeled[n] = $1 } else plain[n] = $1
            }
            END { for (n in plain) print ((n in peeled) ? peeled[n] : plain[n]), n }' <<< "$refs")"

    local commit="$PIN_COMMIT"
    if [ -n "$commit" ] && ! [[ "$commit" =~ ^[0-9a-f]{40}$ ]]; then
        # A short sha: expand it from a ref tip, the only place ls-remote can see it.
        commit="$(awk -v p="$commit" 'index($1, p) == 1 { print $1; exit }' <<< "$heads"$'\n'"$tags")"
        [ -n "$commit" ] || die "ELN_COMMIT=${PIN_COMMIT} is no ref tip on ${REMOTE}; give the full 40-character sha"
    elif [ -z "$commit" ] && [ -n "$PIN_TAG" ]; then
        commit="$(awk -v t="$PIN_TAG" '$2 == t { print $1 }' <<< "$tags")"
        [ -n "$commit" ] || die "no tag ${PIN_TAG} on ${REMOTE}"
    elif [ -z "$commit" ]; then
        commit="$(awk -v b="$PIN_BRANCH" '$2 == b { print $1 }' <<< "$heads")"
        [ -n "$commit" ] || die "no branch ${PIN_BRANCH} on ${REMOTE}"
    fi
    [ "$commit" = "$PIN_COMMIT" ] || { PIN_COMMIT="$commit"; pin_set ELN_COMMIT "$PIN_COMMIT"; }

    if [ -n "$PIN_TAG" ]; then
        local tagged
        tagged="$(awk -v t="$PIN_TAG" '$2 == t { print $1 }' <<< "$tags")"
        [ -z "$tagged" ] || [ "$tagged" = "$PIN_COMMIT" ] \
            || echo "p2d: warning: tag ${PIN_TAG} is ${tagged:0:7}, not ELN_COMMIT ${PIN_COMMIT:0:7}; building the commit" >&2
    else
        # Several tags on one commit: take the highest version.
        PIN_TAG="$(awk -v c="$PIN_COMMIT" '$1 == c { print $2 }' <<< "$tags" | sort -V | tail -n 1)"
        [ -z "$PIN_TAG" ] || pin_set ELN_TAG "$PIN_TAG"
    fi
    if [ -z "$PIN_BRANCH" ]; then
        # Several branches at the commit: prefer main, else the first.
        PIN_BRANCH="$(awk -v c="$PIN_COMMIT" '$1 == c { print $2 }' <<< "$heads" \
                      | awk '{ a[NR] = $0 } $0 == "main" { m = 1 } END { print (m ? "main" : a[1]) }')"
        [ -z "$PIN_BRANCH" ] || pin_set ELN_BRANCH "$PIN_BRANCH"
    fi
}

# The image name of the pinned build: <branch|tag|commit>-<short sha>.
pin_name() { printf '%s' "${PIN_BRANCH:-${PIN_TAG:-commit}}"; }
pin_image() { echo "${IMAGE_REPO}:$(tag_of "$(pin_name)")-${PIN_COMMIT:0:7}"; }

cmd_build() {
    local ref="${1:-}" commit=""
    if [ -z "$ref" ] && [ -f "$PIN_FILE" ]; then
        resolve_pin
        ref="$(pin_name)" commit="$PIN_COMMIT"
        echo "p2d: using $(basename "$PIN_FILE"): ${ref} @ ${commit:0:7}"
    fi
    ref="${ref:-main}"
    mkdir -p "$P2D_DIR"
    # Global, not local: the EXIT trap runs after this function has returned.
    P2D_WORK="$(mktemp -d "${P2D_DIR}/build.XXXXXX")"
    trap 'rm -rf -- "${P2D_WORK:?}"' EXIT
    local work="$P2D_WORK"

    # Dockerfile.p2d reads the commit to check out from .git/shallow, which only a shallow clone
    # has, and which must hold exactly one commit.
    echo "p2d: cloning ${commit:-$ref} from ${REMOTE}"
    if [ -n "$commit" ] || ! git clone -q --depth 1 --branch "$ref" "$REMOTE" "${work}/eln" 2>/dev/null; then
        # A pinned commit, or not a branch or tag: fetch it as a commit.
        local want="${commit:-$ref}"
        rm -rf "${work}/eln"
        git init -q "${work}/eln"
        git -C "${work}/eln" remote add origin "$REMOTE"
        git -C "${work}/eln" fetch -q --depth 1 origin "$want" || die "cannot fetch ${want} from ${REMOTE}"
        git -C "${work}/eln" checkout -q FETCH_HEAD
    fi
    [ -f "${work}/eln/Dockerfile.p2d" ] || die "${ref} has no Dockerfile.p2d (it exists from ELN v3.1.0-rc on)"
    [ "$(wc -l < "${work}/eln/.git/shallow")" -eq 1 ] || die "expected one commit in .git/shallow"

    local sha tag
    sha="$(git -C "${work}/eln" rev-parse HEAD)"
    [ -z "$commit" ] || [ "$sha" = "$commit" ] || die "fetched ${sha}, expected ${commit}"
    sha="${sha:0:7}"
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
    local image
    if [ "$#" -gt 0 ] && [ -n "$1" ] && [[ "$1" != -* ]]; then
        image="$(image_of "$1")"; shift
    elif [ -f "$PIN_FILE" ]; then
        [ "$#" -eq 0 ] || [ -n "$1" ] || shift
        resolve_pin
        image="$(pin_image)"
        docker image inspect "$image" >/dev/null 2>&1 \
            || die "no image ${image} for $(basename "$PIN_FILE"); run: p2d.sh build"
    else
        [ "$#" -eq 0 ] || [ -n "$1" ] || shift
        image="$(image_of main)"
    fi

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
    image) shift
           if [ -n "${1:-}" ]; then image_of "$1"
           elif [ -f "$PIN_FILE" ]; then resolve_pin; pin_image
           else image_of main; fi ;;
    *) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
