#!/usr/bin/env bash

set -Eeuo pipefail

PACKAGE_NAME="axion-ppt-master"
SYSTEM_USER="glenclaw"
SYSTEM_GROUP="glenclaw"
EXPECTED_UID="10001"
EXPECTED_GID="10001"
TARGET_PARENT="/usr/local/axion/skills"
TARGET_DIR="${TARGET_PARENT}/ppt-master"
LOCK_FILE="/usr/local/axion/.axion-ppt-master.install.lock"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_DIR="${SCRIPT_DIR}/payload/usr/local/axion/skills/ppt-master"
STAGE_DIR=""
BACKUP_DIR=""
TARGET_REPLACED=0
COMMITTED=0

fail() {
  printf '%s\n' "${PACKAGE_NAME} install failed: $*" >&2
  exit 1
}

validate_identity() {
  local group_gid
  local group_record
  local user_gid
  local user_uid

  user_uid="$(id -u "${SYSTEM_USER}" 2>/dev/null || true)"
  user_gid="$(id -g "${SYSTEM_USER}" 2>/dev/null || true)"
  [[ "${user_uid}" == "${EXPECTED_UID}" && "${user_gid}" == "${EXPECTED_GID}" ]] || \
    fail "${SYSTEM_USER} must have UID/GID ${EXPECTED_UID}:${EXPECTED_GID}"
  group_record="$(getent group "${SYSTEM_GROUP}" || true)"
  IFS=: read -r _ _ group_gid _ <<<"${group_record}"
  [[ -n "${group_record}" && "${group_gid}" == "${EXPECTED_GID}" ]] || \
    fail "${SYSTEM_GROUP} must exist with GID ${EXPECTED_GID}"
}

cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if [[ "${COMMITTED}" != 1 ]]; then
    [[ -z "${STAGE_DIR}" ]] || rm -rf -- "${STAGE_DIR}"
    if [[ "${TARGET_REPLACED}" == 1 ]]; then
      rm -rf -- "${TARGET_DIR}"
      if [[ -n "${BACKUP_DIR}" && -e "${BACKUP_DIR}" ]]; then
        mv -- "${BACKUP_DIR}" "${TARGET_DIR}"
      fi
    fi
  fi
  exit "${status}"
}

main() {
  [[ "${EUID}" -eq 0 ]] || fail "install.sh must run as root"
  [[ -d "${SOURCE_DIR}" && -f "${SOURCE_DIR}/SKILL.md" ]] || \
    fail "tarball payload is incomplete"
  [[ ! -L "${SCRIPT_DIR}/payload" && ! -L "${SOURCE_DIR}" ]] || \
    fail "tarball payload root must not be a symlink"
  if find "${SOURCE_DIR}" -type l -print -quit | grep -q .; then
    fail "tarball payload must not contain symlinks"
  fi

  validate_identity
  install -d -m 0755 /usr/local/axion "${TARGET_PARENT}"
  [[ -w /usr/local/axion && -w "${TARGET_PARENT}" ]] || \
    fail "/usr/local/axion must be writable"
  exec 9>"${LOCK_FILE}"
  flock -x 9

  STAGE_DIR="$(mktemp -d "${TARGET_PARENT}/.ppt-master.install.XXXXXX")"
  cp -a -- "${SOURCE_DIR}/." "${STAGE_DIR}/"
  chown -R "${SYSTEM_USER}:${SYSTEM_GROUP}" "${STAGE_DIR}"

  if [[ -e "${TARGET_DIR}" || -L "${TARGET_DIR}" ]]; then
    BACKUP_DIR="${TARGET_PARENT}/.ppt-master.backup.$$"
    rm -rf -- "${BACKUP_DIR}"
    mv -- "${TARGET_DIR}" "${BACKUP_DIR}"
  fi
  mv -- "${STAGE_DIR}" "${TARGET_DIR}"
  STAGE_DIR=""
  TARGET_REPLACED=1

  COMMITTED=1
  rm -rf -- "${BACKUP_DIR}"
  trap - EXIT HUP INT TERM
  printf '%s\n' "${PACKAGE_NAME}: installed ${TARGET_DIR}; reboot to activate it"
}

trap cleanup EXIT HUP INT TERM
main "$@"
