#!/usr/bin/env bash
set -euo pipefail

IMAGE_PATH="${IMAGE_PATH:-}"
SEED_BASE_URL="${SEED_BASE_URL:-http://10.0.2.2:8080}"
SEED_TOKEN="${SEED_TOKEN:-}"
VM_NAME="${VM_NAME:-bootstrap-test}"
VM_DISK="${VM_DISK:-./build/${VM_NAME}.qcow2}"
VM_SIZE_GB="${VM_SIZE_GB:-20}"
VM_MEMORY_MB="${VM_MEMORY_MB:-2048}"
VM_CPUS="${VM_CPUS:-2}"
LOG_FILE="${LOG_FILE:-qemu.log}"
UEFI_CODE="${UEFI_CODE:-/opt/homebrew/share/qemu/edk2-aarch64-code.fd}"
UEFI_VARS="${UEFI_VARS:-./build/${VM_NAME}-edk2-vars.fd}"

if [ -z "${IMAGE_PATH}" ] || [ -z "${SEED_TOKEN}" ]; then
  cat >&2 <<EOF
Required environment variables:
  IMAGE_PATH=/path/to/ubuntu-24.04-server-cloudimg-arm64.img
  SEED_TOKEN=<seed token>

Optional:
  SEED_BASE_URL=http://10.0.2.2:8080
  VM_NAME=bootstrap-test
  VM_DISK=./build/bootstrap-test.qcow2
  VM_SIZE_GB=20
  VM_MEMORY_MB=2048
  VM_CPUS=2
  LOG_FILE=qemu.log
  UEFI_CODE=/opt/homebrew/share/qemu/edk2-aarch64-code.fd
  UEFI_VARS=./build/bootstrap-test-edk2-vars.fd
EOF
  exit 1
fi

if ! command -v qemu-system-aarch64 >/dev/null 2>&1; then
  echo "qemu-system-aarch64 is required" >&2
  exit 1
fi

if ! command -v qemu-img >/dev/null 2>&1; then
  echo "qemu-img is required" >&2
  exit 1
fi

mkdir -p "$(dirname "${VM_DISK}")"
mkdir -p "$(dirname "${UEFI_VARS}")"

if [ ! -f "${UEFI_CODE}" ]; then
  echo "Missing UEFI firmware code file: ${UEFI_CODE}" >&2
  exit 1
fi

if [ ! -f "${UEFI_VARS}" ]; then
  truncate -s 64M "${UEFI_VARS}"
fi

if [ ! -f "${VM_DISK}" ]; then
  BACKING_FORMAT="$(qemu-img info --output=json "${IMAGE_PATH}" | python3 -c 'import sys, json; print(json.load(sys.stdin)["format"])')"
  qemu-img create -f qcow2 -F "${BACKING_FORMAT}" -b "${IMAGE_PATH}" "${VM_DISK}" "${VM_SIZE_GB}G"
fi

echo "Image path:    ${IMAGE_PATH}"
echo "Disk:          ${VM_DISK}"
echo "UEFI code:     ${UEFI_CODE}"
echo "UEFI vars:     ${UEFI_VARS}"
echo "Seed URL:      ${SEED_BASE_URL%/}/seed/${SEED_TOKEN}/"
echo "Log file:      ${LOG_FILE}"

exec qemu-system-aarch64 \
  -accel hvf \
  -machine virt,highmem=on \
  -cpu host \
  -m "${VM_MEMORY_MB}" \
  -smp "${VM_CPUS}" \
  -drive if=pflash,format=raw,readonly=on,file="${UEFI_CODE}" \
  -drive if=pflash,format=raw,file="${UEFI_VARS}" \
  -drive if=none,file="${VM_DISK}",format=qcow2,id=hd0 \
  -device virtio-blk-device,drive=hd0 \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device virtio-net-device,netdev=net0 \
  -boot order=c \
  -serial mon:stdio \
  -nographic \
  -d guest_errors \
  -D "${LOG_FILE}" \
  -smbios "type=1,serial=ds=nocloud;s=${SEED_BASE_URL%/}/seed/${SEED_TOKEN}/"