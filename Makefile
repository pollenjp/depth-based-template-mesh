SHELL := bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CMD_DIR := ${ROOT}/.local
BLENDER_DIR := ${CMD_DIR}/blender

# <https://download.blender.org/release/>
BLENDER_VERSION_MAJOR_MINOR := 2.93
BLENDER_CMD := ${BLENDER_DIR}/blender

OUTPUT_DIR := output
DEBUG_BLEND_FILE := ${OUTPUT_DIR}/debug.blend

RUN_PY_FILE := main.py


.PHONY: setup
setup:
	./setup.sh

.PHONY: resetup
resetup:
	rm -rf "${BLENDER_DIR}"
	./setup.sh

.PHONY: lint
lint:
	isort --check --sg '.*' .
	black --check .
	flake8 --exclude '.*' .

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
			config=config/main.yml \
			input.depth_image_path=./data/bench.png \
			output_filepath_obj="${OUTPUT_DIR}/template_out.obj" \
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
