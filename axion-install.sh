#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./axion-install.sh

Install or replace PPT Master at ~/.axion-agent/skills/ppt-master.

Environment:
  AXION_AGENT_HOME  Override ~/.axion-agent for isolated or multi-instance installs.
EOF
}

if [[ $# -gt 0 ]]; then
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SOURCE_DIR="${SCRIPT_DIR}/skills/ppt-master"

if [[ -n "${AXION_AGENT_HOME:-}" ]]; then
    AXION_AGENT_DIR="${AXION_AGENT_HOME}"
else
    if [[ -z "${HOME:-}" ]]; then
        printf 'HOME is not set; cannot determine the Axion Agent directory.\n' >&2
        exit 1
    fi
    AXION_AGENT_DIR="${HOME}/.axion-agent"
fi

if [[ "${AXION_AGENT_DIR}" != /* || "${AXION_AGENT_DIR}" == "/" ]]; then
    printf 'AXION_AGENT_HOME must be an absolute, non-root path: %s\n' \
        "${AXION_AGENT_DIR}" >&2
    exit 1
fi

TARGET_ROOT="${AXION_AGENT_DIR}/skills"
TARGET_DIR="${TARGET_ROOT}/ppt-master"
BACKUP_ROOT="${AXION_AGENT_DIR}/backups/skills"
STAGING_DIR=""

cleanup() {
    if [[ -n "${STAGING_DIR}" && -d "${STAGING_DIR}" ]]; then
        case "${STAGING_DIR}" in
            "${TARGET_ROOT}"/.ppt-master.install.*)
                rm -rf -- "${STAGING_DIR}"
                ;;
        esac
    fi
}
trap cleanup EXIT

if [[ ! -d "${SOURCE_DIR}" || ! -f "${SOURCE_DIR}/SKILL.md" ]]; then
    printf 'PPT Master source directory is incomplete: %s\n' "${SOURCE_DIR}" >&2
    exit 1
fi

mkdir -p -- "${TARGET_ROOT}"
STAGING_DIR="$(mktemp -d "${TARGET_ROOT}/.ppt-master.install.XXXXXX")"
cp -R -- "${SOURCE_DIR}/." "${STAGING_DIR}/"

if [[ ! -f "${STAGING_DIR}/SKILL.md" ]]; then
    printf 'Staged installation is missing SKILL.md: %s\n' "${STAGING_DIR}" >&2
    exit 1
fi

BACKUP_DIR=""
if [[ -e "${TARGET_DIR}" || -L "${TARGET_DIR}" ]]; then
    mkdir -p -- "${BACKUP_ROOT}"
    TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
    BACKUP_DIR="${BACKUP_ROOT}/ppt-master.${TIMESTAMP}.$$"
    mv -- "${TARGET_DIR}" "${BACKUP_DIR}"
fi

if ! mv -- "${STAGING_DIR}" "${TARGET_DIR}"; then
    printf 'Failed to activate the staged installation.\n' >&2
    if [[ -n "${BACKUP_DIR}" && ! -e "${TARGET_DIR}" ]]; then
        mv -- "${BACKUP_DIR}" "${TARGET_DIR}"
        printf 'Restored the previous installation: %s\n' "${TARGET_DIR}" >&2
    fi
    exit 1
fi
STAGING_DIR=""

printf 'Installed PPT Master: %s\n' "${TARGET_DIR}"
if [[ -n "${BACKUP_DIR}" ]]; then
    printf 'Previous installation backed up to: %s\n' "${BACKUP_DIR}"
fi
