#!/usr/bin/env bash
# shellcheck shell=bash
set -eux

# <https://download.blender.org/release/>
BLENDER_VERSION_MAJOR_MINOR="2.93"
BLENDER_VERSION_PATCH="9"
PYTHON_CMD_NAME="python3.9"

BLENDER_RELEASE_NAME="blender-${BLENDER_VERSION_MAJOR_MINOR}.${BLENDER_VERSION_PATCH}-linux-x64"
CMD_DIR="$(realpath .local)"
BLENDER_DIR="${CMD_DIR}/blender"
BLENDER_RELEASE_DIR="${BLENDER_DIR}"
CACHE_DIR="${CMD_DIR}/.cache/blender"
BLENDER_BIN_PATH="${BLENDER_RELEASE_DIR}/bin" # create for adding to PATH
BLENDER_CMD="${BLENDER_RELEASE_DIR}/blender"
BLENDER_PYTHON_PATH="${BLENDER_RELEASE_DIR}/${BLENDER_VERSION_MAJOR_MINOR}/python/bin"

function download_blender () {
	# Use a subshell to avoid changing the current path
	(
		mkdir -p "${CACHE_DIR}"
		cd "${CACHE_DIR}"
		if [[ ! -f "${BLENDER_RELEASE_NAME}.tar.xz" ]]; then
			wget -c "https://download.blender.org/release/Blender${BLENDER_VERSION_MAJOR_MINOR}/${BLENDER_RELEASE_NAME}.tar.xz"
		fi
		tar Jxfv "${CACHE_DIR}/${BLENDER_RELEASE_NAME}.tar.xz"
		mv "${BLENDER_RELEASE_NAME}" "${BLENDER_DIR}"
	)
}
if [[ ! -d ${BLENDER_RELEASE_DIR} ]]; then
	download_blender
fi

function install_blender_python () {
	# Use a subshell to avoid changing the current path
	(
		mkdir -p "${BLENDER_BIN_PATH}"
		if ! [[ -h "${BLENDER_BIN_PATH}/blender" ]]; then
			ln -s "${BLENDER_CMD}" "${BLENDER_BIN_PATH}/blender"
		fi
	)
}
install_blender_python

function create_python_symlink () {
	# Use a subshell to avoid changing the current path
	(
		cd "${BLENDER_PYTHON_PATH}"
		if ! [[ -h "python" ]]; then
			ln -s "${PYTHON_CMD_NAME}" python
		fi
		if ! [[ -h "python3" ]]; then
			ln -s "${PYTHON_CMD_NAME}" python3
		fi
	)
}
create_python_symlink

function install_pip () {
	# Use a subshell to avoid changing the current path
	(
		cd "${BLENDER_PYTHON_PATH}"
		curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
		"./${PYTHON_CMD_NAME}" get-pip.py
	)
}
if [[ ! -f "${BLENDER_PYTHON_PATH}/pip" ]]; then
	install_pip
fi

target_envrc_path=".envrc"
touch "${target_envrc_path}"
line="export PATH=\"${BLENDER_BIN_PATH}:${BLENDER_PYTHON_PATH}:\$PATH"\"
if ! grep -F --quiet "${line}" < "$target_envrc_path"; then
	echo "${line}" | tee -a "${target_envrc_path}"
fi
