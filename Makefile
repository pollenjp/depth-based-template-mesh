SHELL := bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CMD_DIR := ${ROOT}/.local
BLENDER_DIR := ${CMD_DIR}/blender

# <https://download.blender.org/release/>
BLENDER_VERSION_MAJOR_MINOR := 2.93
BLENDER_RELEASE_NAME := blender-${BLENDER_VERSION_MAJOR_MINOR}.5-linux-x64
BLENDER_RELEASE_DIR := ${BLENDER_DIR}/${BLENDER_RELEASE_NAME}

BLENDER_CMD := ${BLENDER_RELEASE_DIR}/blender

DEBUG_BLEND_FILE := debug.blend

# RUN_PY_FILE := generate_sphere.py
RUN_PY_FILE := load_depth_image_and_modify.py


.PHONY: setup
setup:
	./setup.sh

.PHONY: resetup
resetup:
	rm -rf ${BLENDER_RELEASE_DIR}
	./setup.sh

.PHONY: lint
lint:
	isort --check --sg '.*' .
	black --check .
	flake8 --exclude '.*' .

run-blender:
	$(BLENDER_CMD)

##################
# concrete tasks #
##################

.PHONY: debug-blender-python
debug-blender-python:
	${MAKE} clean
	${MAKE} run-blender-python
	${MAKE} run-debug-blend-file

.PHONY: run-blender-python
run-blender-python:
	${BLENDER_CMD} \
		--background \
		--python \
		${RUN_PY_FILE} \
			-- \
			config=config/load_depth_image_and_modify.yaml \
			input.depth_image_path=./data/bench.png \
			output_filepath_obj="template_out.obj" \
			debug.blend_filepath=${DEBUG_BLEND_FILE}

.PHONY: run-debug-blend-file
run-debug-blend-file:
	${MAKE} kill
# error if not exists
	[[ -f ${DEBUG_BLEND_FILE} ]]

# open an image
#	eog ${ROOT}/sample_output.png &

# run blender
	${BLENDER_CMD} ${DEBUG_BLEND_FILE} &

.PHONY: kill
kill:
	-killall eog
	-killall ${BLENDER_CMD}

################################################################################

.PHONY: clean
clean:
	-rm -rf ${DEBUG_BLEND_FILE}
	-rm -rf sample_output.png
