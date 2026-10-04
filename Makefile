\
# ============================================================
# SpecTalkZX Makefile (w64devkit-friendly, ASCII-safe)
# Default pipeline: CHECK -> CLEAN -> BUILD -> INFO
# - Spinner (works with /bin/sh)
# - Preflight dependency checks
# - `make` runs clean automatically
# ============================================================

.DEFAULT_GOAL := all

# ------------------------------------------------------------
# Toolchain / target
# ------------------------------------------------------------
CC      = zcc
TARGET  = +zx
PYTHON  ?= python3

# ------------------------------------------------------------
# Project
# ------------------------------------------------------------
OUTPUT  = SpecTalkZX
TAP     = $(BUILD_DIR)/$(OUTPUT).tap
MAP     = $(OUTPUT).map
BUILD_DIR = build
LOG     = $(BUILD_DIR)/build.log
BPE_STAMP = $(BUILD_DIR)/.bpe.stamp
TOOLCHAIN_VERSION = $(BUILD_DIR)/toolchain.version
EVIDENCE_DIR = $(BUILD_DIR)/evidence
SPXN_BOOTSTRAP_SIZE = 256
NEX     = $(BUILD_DIR)/SPECTALK.NEX
NEXT_RAW_CODE = $(OUTPUT)__.bin
NEXT_RESIDENT = $(BUILD_DIR)/next-resident.img

# ------------------------------------------------------------
# Sources
# ------------------------------------------------------------
C_SOURCES    = src/main_build.c

PLATFORM ?= classic
SPXN_DIR ?=
SKIP_CHECK ?= 0

ifeq ($(PLATFORM),next)
TARGET = +zxn
ASM_SOURCES = asm/next_uart.asm asm/next_clock.asm asm/next_data.asm asm/spectalk_asm.asm asm/next_overlay_loader.asm
TARGET_FLAGS = -DSPECTALK_NEXT -Ca-DSPECTALK_NEXT
TARGET_ASM_FLAGS = -DSPECTALK_NEXT
OVERLAY_LOAD_ADDR = 2000
OVERLAY_CAP = 8190
UART_DESC = ZX Spectrum Next internal ESP UART (115200 baud)
RESIDENT_TARGET = $(NEXT_RESIDENT)
else ifeq ($(PLATFORM),spectranext)
ifeq ($(strip $(SPXN_DIR)),)
$(error SPXN_DIR must point to the Spectranext driver directory)
endif
override SPXN_DIR := $(subst \,/,$(SPXN_DIR))
override SPXN_DIR := $(abspath $(SPXN_DIR))
C_SOURCES += $(SPXN_DIR)/spxresolve.c
ASM_SOURCES  = asm/spectalk_asm.asm asm/overlay_loader.asm \
               $(SPXN_DIR)/spxn_rom.asm \
               $(SPXN_DIR)/adapters/xfs_compat.asm
TARGET_FLAGS = -DSPECTALK_SPECTRANEXT -Ca-DSPECTALK_SPECTRANEXT \
               -DSPXN_ROM_HELD -Ca-DSPXN_ROM_HELD \
               -Ca-DSPXN_XFS_KEEP_HANDLES \
               -Ca-DSPXN_XFS_STATE_BASE=0x5B80 \
               -Ca-DSPXN_XFS_DIR_SCRATCH=0x5CB6 \
               -Ca-DSPXN_XFS_SCRATCH_PRESERVE_BASE=0x5CB6 \
               -Ca-DSPXN_XFS_SCRATCH_PRESERVE_SIZE=128 \
               -Ca-DSPXN_XFS_SCRATCH_PRESERVE_BACKUP=0x5B00 \
               -I$(SPXN_DIR)
TARGET_ASM_FLAGS = -DSPECTALK_SPECTRANEXT -DSPXN_ROM_HELD
OVERLAY_LOAD_ADDR = 2000
OVERLAY_CAP = 4096
UART_DESC = Spectranext ROM sockets (no UART/ESP-AT)
RESIDENT_TARGET = $(TAP)
else
ASM_SOURCES  = asm/divmmc_uart.asm asm/spectalk_asm.asm asm/overlay_loader.asm
TARGET_FLAGS =
TARGET_ASM_FLAGS =
OVERLAY_LOAD_ADDR =
OVERLAY_CAP = 2048
UART_DESC = divMMC/divTiesus (115200 baud)
RESIDENT_TARGET = $(TAP)
endif

# ------------------------------------------------------------
# Build options
# ------------------------------------------------------------
ASM_MODULE_SOURCES = asm/spectalk_asm/00_preamble.asm \
                     asm/spectalk_asm/10_core_helpers.asm \
                     asm/spectalk_asm/20_rx_ring_uart.asm \
                     asm/spectalk_asm/30_rendering.asm \
                     asm/spectalk_asm/40_text_numeric_screen.asm \
                     asm/spectalk_asm/50_main_output.asm \
                     asm/spectalk_asm/60_protocol_storage.asm \
                     asm/spectalk_asm/70_input_lookup.asm \
                     asm/spectalk_asm/80_ui_runtime.asm
ASM_DEP_SOURCES = $(ASM_SOURCES) $(ASM_MODULE_SOURCES)
BPE_INPUTS = src/spectalk.c src/config_load.c src/config_apply.c src/irc_handlers.c src/user_cmds.c src/net_classic.c src/clock_classic.c \
             src/net_spectranext.c src/clock_spectranext.c \
             include/spectalk.h include/spectalk_net.h include/spectalk_clock.h \
             src/SPECTALK.DAT src/SPECTALK_HELP.txt overlay/overlay_api.h overlay/xfs_write_ovl.asm overlay/esx_write_ovl.asm \
             overlay/overlay_entry2.asm overlay/earth_about_render.asm \
             tools/bpe_build.py tools/bpe_compress.py \
             release/about_earth/earth_frame0.compact.bin \
             release/about_earth/earth_frame_deltas.bin \
             release/about_earth/earth_attr0.compact4.bin \
             release/about_earth/earth_attr_deltas.compact4.bin \
             release/about_earth/earth_logo.bin \
             tools/gen_whatsnew.py release/logo.png release/changes.txt release/version.txt
ZORG        = 24000
STACK_SIZE  = 512
BSS_RING_GUARD ?= 96
BSS_RING_WARN  ?= 128

MAX_ALLOCS_PER_NODE ?= 200000
MAX_ALLOC_CFLAGS = --max-allocs-per-node$(MAX_ALLOCS_PER_NODE)
EXTRA_CFLAGS ?=
BUILD_PROFILE ?= NORMAL
EVIDENCE ?= 0
ifeq ($(EVIDENCE),1)
ZCC_EVIDENCE_FLAGS = -s --list --lstcwd
Z80ASM_EVIDENCE_FLAGS = -s -l
else
ZCC_EVIDENCE_FLAGS =
Z80ASM_EVIDENCE_FLAGS =
endif
ZCC_EVIDENCE_FLAGS += $(TARGET_FLAGS)
Z80ASM_EVIDENCE_FLAGS += $(TARGET_ASM_FLAGS)
CFLAGS = -vn -SO3 -startup=31 -compiler=sdcc -clib=sdcc_iy \
         -zorg=$(ZORG) --opt-code-size --fomit-frame-pointer \
         -Cc--Werror \
         -custom-copt-rules=src/spectalk_copt.rul \
         -pragma-define:CLIB_MALLOC_HEAP_SIZE=0 \
         -pragma-define:CLIB_STDIO_HEAP_SIZE=0 \
         -pragma-define:CRT_STACK_SIZE=$(STACK_SIZE) \
         -pragma-define:CRT_ENABLE_STDIO=0 \
         -Wl,--gc-sections -Wall $(ZCC_EVIDENCE_FLAGS)
# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
SIZE_TAP  = wc -c < "$(TAP)"
BUILD_CMD = $(CC) $(TARGET) $(CFLAGS) $(EXTRA_CFLAGS) $(MAX_ALLOC_CFLAGS) $(C_SOURCES) $(ASM_SOURCES) -m -o $(OUTPUT) -create-app
NEXT_BUILD_CMD = $(CC) $(TARGET) -subtype=bin $(CFLAGS) $(EXTRA_CFLAGS) $(MAX_ALLOC_CFLAGS) $(C_SOURCES) $(ASM_SOURCES) -m -o $(OUTPUT) -create-app

# ------------------------------------------------------------
# ANSI colors (disable with NO_COLOR=1)
# IMPORTANT: keep escapes as *literal* backslashes to avoid embedding ESC/CR chars in Makefile.
# ------------------------------------------------------------
ifeq ($(NO_COLOR),1)
C_RESET :=
C_BOLD  :=
C_DIM   :=
C_RED   :=
C_GRN   :=
C_YEL   :=
C_BLU   :=
C_CYNB  :=
else
C_RESET := \\033[0m
C_BOLD  := \\033[1m
C_DIM   := \\033[2m
C_RED   := \\033[31m
C_GRN   := \\033[32m
C_YEL   := \\033[33m
C_BLU   := \\033[34m
C_CYNB  := \\033[96m
endif

# ------------------------------------------------------------
# Pretty printing
# ------------------------------------------------------------
define HR
	@printf "$(C_DIM)============================================================$(C_RESET)\n"
endef

define STEP
	@printf "$(C_BOLD)$(C_BLU)[%s]$(C_RESET) %s\n" "$(1)" "$(2)"
endef

define OK
	@printf "$(C_GRN)[OK]$(C_RESET) %s\n" "$(1)"
endef

define WARN
	@printf "$(C_YEL)[WARN]$(C_RESET) %s\n" "$(1)"
endef

define ERR
	@printf "$(C_RED)[ERR]$(C_RESET) %s\n" "$(1)"
endef


# ------------------------------------------------------------
# Phony targets
# ------------------------------------------------------------
.PHONY: all check clean bpe build restore_bpe trim overlay overlay_build _overlay_build info help evidence gather_evidence release RELEASE toolchain_guard next next-all next-check nex-build next-info spectranext test-spectranext-network test-spectranext-storage test-spectranext-configuration test-spectranext-clock

# ------------------------------------------------------------
# Default pipeline
# ------------------------------------------------------------
all:
	@status=0; \
	if [ "$(SKIP_CHECK)" != "1" ]; then $(MAKE) --no-print-directory check || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory clean || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory $(BPE_STAMP) || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory $(TAP) || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory trim overlay info || status=$$?; fi; \
	$(MAKE) --no-print-directory restore_bpe || exit $$?; \
	exit $$status

help:
	$(call HR)
	@printf "Targets:\n"
	@printf "  make            - CHECK -> CLEAN -> BUILD -> INFO\n"
	@printf "  make release    - Release build (max optimization)\n"
	@printf "  make check      - Preflight dependency checks\n"
	@printf "  make clean      - Remove build artifacts\n"
	@printf "  make build      - Run BPE prep + build $(TAP) + restore sources\n"
	@printf "  make next       - Build only the native Spectrum Next NEX\n"
	@printf "  make info       - Report an existing build (read-only)\n"
	@printf "  make evidence   - Full build plus compiler/assembler evidence\n"
	@printf "\nOptions:\n"
	@printf "  NO_COLOR=1      - Disable ANSI colors\n"
	$(call HR)

# ------------------------------------------------------------
# CHECK phase
# ------------------------------------------------------------
check: toolchain_guard
	$(call HR)
	@printf "$(C_BOLD)$(C_CYNB)SpecTalkZX - Build Pipeline$(C_RESET)\n"
	$(call HR)
	$(call STEP,0/4,Checking toolchain and sources)
	@mkdir -p $(BUILD_DIR)
	@sh -c '\
		fail=0; \
		for t in zcc z80asm z88dk-appmake z88dk-copt wc sh grep sed head tail cat dd; do \
			command -v "$$t" >/dev/null 2>&1 || { echo "[ERR] Missing tool: $$t"; fail=1; }; \
		done; \
		$(PYTHON) -c "import sys; raise SystemExit(sys.version_info < (3, 8))" >/dev/null 2>&1 || { echo "[ERR] Missing usable Python 3: $(PYTHON)"; fail=1; }; \
		for f in $(C_SOURCES) $(ASM_DEP_SOURCES) $(BPE_INPUTS) overlay/spxn_page_loader.asm tools/gen_whatsnew.py release/logo.png release/changes.txt release/version.txt; do \
			[ -f "$$f" ] || { echo "[ERR] Missing file: $$f"; fail=1; }; \
		done; \
		[ "$$fail" = "0" ] || exit 2; \
	'
	@$(PYTHON) tools/test_bpe_transaction.py
	@$(PYTHON) tools/test_bpe_notification_strings.py
	@$(PYTHON) tools/test_config_keys.py
	@$(PYTHON) tools/test_network_seam.py
	@$(PYTHON) tools/test_spectranext_release_blockers.py
	@$(PYTHON) tools/test_spectranext_audit_followups.py
	@$(PYTHON) tools/test_clock_seam.py
	@$(PYTHON) tools/test_earth_packet_bounds.py
	@$(PYTHON) tools/test_udp_tx_timeout.py
	@$(PYTHON) tools/test_transport_integrity.py
	@$(PYTHON) tools/test_overlay_validation.py
	@$(PYTHON) tools/test_ui_protocol_validation.py
	@$(PYTHON) tools/test_rtc_validation.py
	@$(PYTHON) tools/test_copt_label_safety.py
	@$(PYTHON) tools/test_scroll_contract.py
	@$(PYTHON) tools/check_memory_layout.py --self-test
	@$(PYTHON) tools/test_esxdos_cache_contract.py
	@$(PYTHON) tools/test_registration_error.py
	@$(PYTHON) tools/test_copt_contract.py
	$(call OK,Dependencies OK)
	$(call HR)

toolchain_guard:
	@mkdir -p "$(BUILD_DIR)"
	@version="$$($(CC) --version 2>&1 | sed -n 's/^zcc - Frontend for the z88dk Cross-C Compiler - //p' | head -1)"; \
	if [ -z "$$version" ]; then \
		echo "[ERR] Unable to identify compiler selected by CC=$(CC)"; \
		exit 2; \
	fi; \
	{ echo "CC=$(CC)"; echo "TARGET=$(TARGET)"; echo "zcc=$$version"; } >"$(TOOLCHAIN_VERSION)"; \
	echo "[OK] Compiler recorded in $(TOOLCHAIN_VERSION)"

# ------------------------------------------------------------
# CLEAN phase
# ------------------------------------------------------------
clean:
	@$(MAKE) --no-print-directory restore_bpe
	$(call STEP,1/4,Cleaning)
	@echo "Cleaning build artifacts..."
	@rm -f "$(OUTPUT)" "$(OUTPUT).tap" "$(TAP)" "$(MAP)" "$(LOG)" "$(NEX)" "$(NEXT_RESIDENT)" "$(BUILD_DIR)/SPECTALK.DAT" "$(BUILD_DIR)"/*.OVL *.o *.bin *.sym overlay/*.o 2>/dev/null || true
	@rm -f src/*.lis src/*.sym asm/*.lis asm/*.sym overlay/*.lis overlay/*.sym *.lis *.sym "$(BUILD_DIR)"/*.lis "$(BUILD_DIR)"/*.sym 2>/dev/null || true
	@rm -rf "$(EVIDENCE_DIR)" "$(BUILD_DIR)/bpe_src" "$(BUILD_DIR)/bpe_final" "$(BUILD_DIR)/bpe_dict.bin" "$(BUILD_DIR)"/bpe_originals.tmp-* "$(BPE_STAMP)" "$(BPE_STAMP).tmp" 2>/dev/null || true
	$(call OK,Clean complete.)
	$(call HR)

# ------------------------------------------------------------
# BPE phase - compress screen-only strings
# Reads src/*.c (originals), generates build/bpe_final/*.c (compressed)
# Also generates SPECTALK.DAT with BPE dict inserted
# ------------------------------------------------------------
bpe:
	@status=0; \
	$(MAKE) --no-print-directory $(BPE_STAMP) || status=$$?; \
	$(MAKE) --no-print-directory restore_bpe || exit $$?; \
	exit $$status

spectranext:
	@$(PYTHON) tools/test_spectranext_driver_contract.py "$(SPXN_DIR)"
	@$(MAKE) --no-print-directory PLATFORM=spectranext SPXN_DIR="$(SPXN_DIR)" all

.PHONY: spectranext-direct
spectranext-direct: spectranext
	@$(PYTHON) tools/build_spectranext_direct.py "$(SPXN_DIR)"
	@$(PYTHON) tools/test_spectranext_direct.py

next:
	@$(MAKE) --no-print-directory PLATFORM=next next-all

next-all:
	@status=0; \
	$(MAKE) --no-print-directory clean || status=$$?; \
	if [ "$$status" -eq 0 ] && [ "$(SKIP_CHECK)" != "1" ]; then $(MAKE) --no-print-directory next-check || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory next-info || status=$$?; fi; \
	$(MAKE) --no-print-directory restore_bpe || exit $$?; \
	exit $$status

next-check: check
	@$(PYTHON) -m py_compile tools/gen_next_nex.py tools/test_next_nex_image.py tools/test_next_runtime_contract.py
	@$(PYTHON) tools/test_next_runtime_contract.py
	@$(PYTHON) tools/test_next_earth.py
	$(call OK,Native Next prerequisites OK)

test-spectranext-network:
	@$(PYTHON) tools/test_spectranext_port.py network

test-spectranext-storage:
	@$(PYTHON) tools/test_spectranext_port.py storage

test-spectranext-configuration:
	@$(PYTHON) tools/test_spectranext_port.py configuration

test-spectranext-clock:
	@$(PYTHON) tools/test_spectranext_port.py clock

$(BPE_STAMP): $(BPE_INPUTS)
	$(call STEP,2/4,BPE compression)
	@rm -f "$(BPE_STAMP)" "$(BPE_STAMP).tmp"
	@$(PYTHON) tools/bpe_build.py
	@printf "ok\n" > "$(BPE_STAMP).tmp"
	@mv -f "$(BPE_STAMP).tmp" "$(BPE_STAMP)"
	$(call OK,BPE complete.)
	$(call HR)

# ------------------------------------------------------------
# BUILD phase (only place where zcc is invoked)
# ------------------------------------------------------------
build:
	@status=0; \
	$(MAKE) --no-print-directory toolchain_guard || status=$$?; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory $(BPE_STAMP) || status=$$?; fi; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory $(TAP) || status=$$?; fi; \
	$(MAKE) --no-print-directory restore_bpe || exit $$?; \
	exit $$status

restore_bpe:
	@$(PYTHON) tools/bpe_build.py --restore
	@rm -f "$(BPE_STAMP)" "$(BPE_STAMP).tmp"

$(TAP): $(C_SOURCES) $(ASM_DEP_SOURCES) $(BPE_STAMP)
	$(call STEP,3/4,Build)
	@echo "Compiling SpecTalkZX..."
	@echo "UART mode: $(UART_DESC)"
	@if [ "$(BUILD_PROFILE)" != "NORMAL" ]; then printf "$(C_BOLD)$(C_YEL)Build profile: $(BUILD_PROFILE)$(C_RESET)\n"; fi
	@echo "Log: $(LOG)"
	@rm -f "$(OUTPUT).tap" "$(TAP)"
	@build_rc=0; $(BUILD_CMD) >"$(LOG)" 2>&1 || build_rc=$$?; \
	cat "$(LOG)"; \
	if [ "$$build_rc" -ne 0 ]; then \
		printf "$(C_RED)[FAILED]$(C_RESET) Compilation errors (see $(LOG)):\n"; \
		tail -20 "$(LOG)"; \
		rm -f "$(OUTPUT).tap" "$(TAP)"; \
		exit "$$build_rc"; \
	fi
	@mv "$(OUTPUT).tap" "$(TAP)"
	$(call OK,Build complete.)
	$(call HR)

$(NEXT_RAW_CODE): $(C_SOURCES) $(ASM_DEP_SOURCES) $(BPE_STAMP)
	$(call STEP,3/4,Native Next resident)
	@rm -f "$(OUTPUT)" "$(NEXT_RAW_CODE)" "$(OUTPUT)_CODE.bin" "$(MAP)"
	@build_rc=0; $(NEXT_BUILD_CMD) >"$(LOG)" 2>&1 || build_rc=$$?; \
	cat "$(LOG)"; \
	if [ "$$build_rc" -ne 0 ]; then tail -20 "$(LOG)"; exit "$$build_rc"; fi
	@test -f "$(NEXT_RAW_CODE)" || { echo "[ERR] Missing $(NEXT_RAW_CODE)"; exit 1; }

$(NEXT_RESIDENT): $(NEXT_RAW_CODE)
	@bss=$$(grep "__data_compiler_tail" $(MAP) | grep -o "\$$[0-9A-Fa-f]*" | head -1 | tr -d "\$$"); \
	test -n "$$bss" || { echo "[ERR] __data_compiler_tail missing"; exit 1; }; \
	trim=$$($(PYTHON) -c "print(0x$$bss - $(ZORG))"); \
	head -c $$trim "$(NEXT_RAW_CODE)" >"$(NEXT_RESIDENT)"; \
	printf "$(C_GRN)[OK]$(C_RESET) Next resident: %d bytes\n" "$$trim"
	@$(PYTHON) tools/check_memory_layout.py "$(MAP)" --platform next --bss-guard "$(BSS_RING_GUARD)" --bss-warn "$(BSS_RING_WARN)"

# ------------------------------------------------------------
# TRIM phase - strip BSS zeros from TAP (saves ~4KB)
# BSS is zeroed at startup by code_crt_init in spectalk_asm.asm
# ------------------------------------------------------------
trim: $(TAP) $(MAP)
	@sh -c ' \
	  bss=$$(grep "__data_compiler_tail" $(MAP) | grep -o "\$$[0-9A-Fa-f]*" | head -1 | tr -d "\$$"); \
	  if [ -z "$$bss" ]; then \
	    printf "$(C_YEL)[WARN]$(C_RESET) BSS trim skipped (symbol not found in map)\n"; \
	    exit 0; \
	  fi; \
	  trim=$$($(PYTHON) -c "print(0x$$bss - $(ZORG))"); \
	  bin="$(OUTPUT)_CODE.bin"; \
	  if [ ! -s "$$bin" ]; then bin="$(OUTPUT)"; fi; \
	  if [ ! -s "$$bin" ]; then \
	    printf "$(C_YEL)[WARN]$(C_RESET) BSS trim skipped (binary not found)\n"; \
	    exit 0; \
	  fi; \
	  full=$$(wc -c < "$$bin"); \
	  saved=$$((full - trim)); \
	  head -c $$trim "$$bin" > $(BUILD_DIR)/trimmed.bin; \
	  z88dk-appmake +zx -b $(BUILD_DIR)/trimmed.bin --org $(ZORG) --blockname SpecTalkZX --usraddr $(ZORG) -o $(TAP) 2>/dev/null; \
	  rm -f $(BUILD_DIR)/trimmed.bin; \
	  printf "$(C_GRN)[OK]$(C_RESET) BSS trimmed: %d -> %d bytes (-%d bytes of zeros)\n" "$$full" "$$trim" "$$saved"; \
	'
	@$(PYTHON) tools/check_memory_layout.py "$(MAP)" --platform "$(PLATFORM)" --bss-guard "$(BSS_RING_GUARD)" --bss-warn "$(BSS_RING_WARN)"

# ------------------------------------------------------------
# OVERLAY phase - compile help_overlay.c against resident symbols
# Pipeline: .map -> overlay_defs.asm -> compile C -> link OVL
# ------------------------------------------------------------
OVL_SRC   = overlay/spectalk_ovl.c
OVL_ENTRY = overlay/overlay_entry.asm
OVL_API   = overlay/overlay_api.h
OVL_OUT   = $(BUILD_DIR)/SPCTLK1.OVL
OVL_DEFS  = $(BUILD_DIR)/overlay_defs.asm

overlay:
	@status=0; \
	$(MAKE) --no-print-directory $(BPE_STAMP) || status=$$?; \
	if [ "$$status" -eq 0 ]; then $(MAKE) --no-print-directory _overlay_build || status=$$?; fi; \
	$(MAKE) --no-print-directory restore_bpe || exit $$?; \
	exit $$status

overlay_build: overlay

_overlay_build: $(RESIDENT_TARGET)
	$(call STEP,OVL,Building overlay)
	@rm -f $(BUILD_DIR)/SPECTALK.OVL $(BUILD_DIR)/SPECTALK.FIXED.OVL $(BUILD_DIR)/SPCTLK[1-8].OVL
	@OVL_ZCC='zcc +z80 -clib=sdcc_iy --no-crt --opt-code-size $(ZCC_EVIDENCE_FLAGS) -Ioverlay'; \
	OVL_ASM='z80asm $(Z80ASM_EVIDENCE_FLAGS)'; \
	SLOT="$(OVERLAY_LOAD_ADDR)"; \
	if [ -z "$$SLOT" ]; then SLOT=$$(grep '_ring_buffer ' $(MAP) | sed -n 's/.*= \$$\([0-9A-Fa-f]*\).*/\1/p' | head -1); fi; \
	if [ -z "$$SLOT" ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) _overlay_slot not found in $(MAP)\n"; \
		exit 1; \
	fi; \
	echo "  overlay_slot = 0x$$SLOT"; \
	$(PYTHON) tools/gen_overlay_defs.py $(MAP) > $(OVL_DEFS) || exit 1; \
	echo "  overlay_defs.asm generated"; \
	$$OVL_ASM $(OVL_DEFS) 2>&1 || exit 1; \
	if [ "$(PLATFORM)" = "spectranext" ]; then \
		$$OVL_ASM -I$(BUILD_DIR) overlay/spxn_page_loader.asm 2>&1 || exit 1; \
		$$OVL_ASM -b -r0xF540 -o=$(BUILD_DIR)/SPXLOAD.OVL \
			overlay/spxn_page_loader.o $(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
		spxload_size=$$(wc -c < $(BUILD_DIR)/SPXLOAD.OVL); \
		if [ "$$spxload_size" -gt $(SPXN_BOOTSTRAP_SIZE) ]; then \
			printf "$(C_RED)[ERR]$(C_RESET) SPXLOAD.OVL too large: $$spxload_size bytes (max $(SPXN_BOOTSTRAP_SIZE))\n"; \
			exit 1; \
		fi; \
		printf "$(C_GRN)[OK]$(C_RESET) SPXLOAD.OVL: $$spxload_size bytes (max $(SPXN_BOOTSTRAP_SIZE))\n"; \
	fi; \
	$$OVL_ZCC -c $(OVL_SRC) -o $(BUILD_DIR)/spectalk_ovl.o 2>&1 || exit 1; \
	echo "  spectalk_ovl.c compiled"; \
	$$OVL_ASM -I$(BUILD_DIR) $(OVL_ENTRY) 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(OVL_OUT) \
		overlay/overlay_entry.o \
		$(BUILD_DIR)/spectalk_ovl.o \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl_size=$$(wc -c < $(OVL_OUT)); \
	if [ "$$ovl_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) Overlay too large: $$ovl_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK1.OVL: $$ovl_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK2.OVL..."; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry2.asm 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) -Irelease/about_earth overlay/earth_about_render.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK2.OVL \
		overlay/overlay_entry2.o \
		overlay/earth_about_render.o \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl2_size=$$(wc -c < $(BUILD_DIR)/SPCTLK2.OVL); \
	if [ "$$ovl2_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK2.OVL too large: $$ovl2_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK2.OVL: $$ovl2_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK3.OVL..."; \
	$(PYTHON) tools/gen_whatsnew.py 2>&1 || exit 1; \
	$$OVL_ZCC -c overlay/spectalk_ovl3.c -o $(BUILD_DIR)/spectalk_ovl3.o 2>&1 || exit 1; \
	$$OVL_ZCC -c overlay/bookmark_store_ovl.c -o $(BUILD_DIR)/bookmark_store_ovl.o 2>&1 || exit 1; \
	if [ "$(PLATFORM)" != "spectranext" ]; then $$OVL_ASM -I$(BUILD_DIR) overlay/esx_write_ovl.asm 2>&1 || exit 1; fi; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry3.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK3.OVL \
		overlay/overlay_entry3.o \
		$(BUILD_DIR)/spectalk_ovl3.o \
		$(if $(filter-out spectranext,$(PLATFORM)),$(BUILD_DIR)/bookmark_store_ovl.o) \
		$(if $(filter-out spectranext,$(PLATFORM)),overlay/esx_write_ovl.o) \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl3_size=$$(wc -c < $(BUILD_DIR)/SPCTLK3.OVL); \
	if [ "$$ovl3_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK3.OVL too large: $$ovl3_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK3.OVL: $$ovl3_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK4.OVL..."; \
	$$OVL_ZCC -c overlay/spectalk_ovl4.c -o $(BUILD_DIR)/spectalk_ovl4.o 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry4.asm 2>&1 || exit 1; \
	if [ "$(PLATFORM)" = "spectranext" ]; then \
		$$OVL_ASM -I$(BUILD_DIR) overlay/xfs_write_ovl.asm 2>&1 || exit 1; \
	fi; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK4.OVL \
		overlay/overlay_entry4.o \
		$(BUILD_DIR)/spectalk_ovl4.o \
		$(if $(filter spectranext,$(PLATFORM)),$(BUILD_DIR)/bookmark_store_ovl.o) \
		$(if $(filter spectranext,$(PLATFORM)),overlay/xfs_write_ovl.o) \
		$(if $(filter-out spectranext,$(PLATFORM)),overlay/esx_write_ovl.o) \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl4_size=$$(wc -c < $(BUILD_DIR)/SPCTLK4.OVL); \
	if [ "$$ovl4_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK4.OVL too large: $$ovl4_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK4.OVL: $$ovl4_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK5.OVL..."; \
	$$OVL_ZCC -c overlay/spectalk_ovl5.c -o $(BUILD_DIR)/spectalk_ovl5.o 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry5.asm 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/rtc_seed_ovl.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK5.OVL \
		overlay/overlay_entry5.o \
		overlay/rtc_seed_ovl.o \
		$(BUILD_DIR)/spectalk_ovl5.o \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl5_size=$$(wc -c < $(BUILD_DIR)/SPCTLK5.OVL); \
	if [ "$$ovl5_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK5.OVL too large: $$ovl5_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK5.OVL: $$ovl5_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK6.OVL..."; \
	$$OVL_ZCC -c overlay/switcher_ovl.c -o $(BUILD_DIR)/switcher_ovl.o 2>&1 || exit 1; \
	if [ "$(PLATFORM)" = "spectranext" ]; then \
		$$OVL_ZCC -c overlay/spectranext_clock_ovl.c -o $(BUILD_DIR)/spectranext_clock_ovl.o 2>&1 || exit 1; \
	fi; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry6.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK6.OVL \
		overlay/overlay_entry6.o \
		$(BUILD_DIR)/switcher_ovl.o \
		$(if $(filter spectranext,$(PLATFORM)),$(BUILD_DIR)/spectranext_clock_ovl.o) \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl6_size=$$(wc -c < $(BUILD_DIR)/SPCTLK6.OVL); \
	if [ "$$ovl6_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK6.OVL too large: $$ovl6_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK6.OVL: $$ovl6_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK7.OVL..."; \
	$$OVL_ZCC -c overlay/local_cmds_ovl.c -o $(BUILD_DIR)/local_cmds_ovl.o 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry7.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK7.OVL \
		overlay/overlay_entry7.o \
		$(BUILD_DIR)/local_cmds_ovl.o \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl7_size=$$(wc -c < $(BUILD_DIR)/SPCTLK7.OVL); \
	if [ "$$ovl7_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK7.OVL too large: $$ovl7_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK7.OVL: $$ovl7_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Building SPCTLK8.OVL..."; \
	$$OVL_ZCC -c overlay/bookmarks_ovl.c -o $(BUILD_DIR)/bookmarks_ovl.o 2>&1 || exit 1; \
	$$OVL_ASM -I$(BUILD_DIR) overlay/overlay_entry8.asm 2>&1 || exit 1; \
	$$OVL_ASM -b -r0x$$SLOT -o=$(BUILD_DIR)/SPCTLK8.OVL \
		overlay/overlay_entry8.o \
		$(BUILD_DIR)/bookmarks_ovl.o \
		$(BUILD_DIR)/overlay_defs.o 2>&1 || exit 1; \
	ovl8_size=$$(wc -c < $(BUILD_DIR)/SPCTLK8.OVL); \
	if [ "$$ovl8_size" -gt $(OVERLAY_CAP) ]; then \
		printf "$(C_RED)[ERR]$(C_RESET) SPCTLK8.OVL too large: $$ovl8_size bytes (max $(OVERLAY_CAP))\n"; \
		exit 1; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) SPCTLK8.OVL: $$ovl8_size bytes (max $(OVERLAY_CAP))\n"; \
	echo "  Packing SPECTALK.OVL atlas..."; \
	dd if=$(BUILD_DIR)/SPCTLK1.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK2.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=1 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK3.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=2 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK4.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=3 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK5.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=4 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK6.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=5 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK7.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=6 2>/dev/null; \
	dd if=$(BUILD_DIR)/SPCTLK8.OVL of=$(BUILD_DIR)/SPECTALK.FIXED.OVL bs=$(OVERLAY_CAP) conv=sync seek=7 2>/dev/null; \
	$(PYTHON) tools/overlay_atlas_probe.py \
		--packed $(BUILD_DIR)/SPECTALK.FIXED.OVL \
		--out $(BUILD_DIR)/SPECTALK.OVL \
		--block-size $(OVERLAY_CAP) \
		$(if $(filter spectranext,$(PLATFORM)),--prefix $(BUILD_DIR)/SPXLOAD.OVL --prefix-size $(SPXN_BOOTSTRAP_SIZE)) \
		--sizes "$$ovl_size,$$ovl2_size,$$ovl3_size,$$ovl4_size,$$ovl5_size,$$ovl6_size,$$ovl7_size,$$ovl8_size" || exit 1; \
	printf "$(C_GRN)[OK]$(C_RESET) SPECTALK.OVL: $$(wc -c < $(BUILD_DIR)/SPECTALK.OVL) bytes (STOA atlas)\n"; \
	rm -f $(BUILD_DIR)/SPCTLK[1-8].OVL $(BUILD_DIR)/SPXLOAD.OVL $(BUILD_DIR)/SPECTALK.FIXED.OVL; \
	echo "  Cleaning build intermediates..."; \
	rm -f $(BUILD_DIR)/*.o \
		$(BUILD_DIR)/SPECTALK $(BUILD_DIR)/SP2.OVL \
		$(BUILD_DIR)/SPECTALK.FIXED.OVL \
		overlay/*.o $(NEXT_RAW_CODE) $(OUTPUT)_CODE.bin 2>/dev/null; \
	if [ "$(EVIDENCE)" != "1" ]; then \
		rm -f $(BUILD_DIR)/*.asm $(BUILD_DIR)/*.bin 2>/dev/null; \
		rm -rf $(BUILD_DIR)/bpe_src $(BUILD_DIR)/bpe_final 2>/dev/null; \
	fi; \
	printf "$(C_GRN)[OK]$(C_RESET) Build artifacts cleaned\n"
	@test -s "$(BUILD_DIR)/SPECTALK.OVL" || { printf "$(C_RED)[ERR]$(C_RESET) Missing or empty $(BUILD_DIR)/SPECTALK.OVL\n"; exit 1; }
	$(call HR)

nex-build: overlay_build
	$(call STEP,NEX,Embedding native Next banks)
	@mkdir -p "$(BUILD_DIR)/SYS/CONFIG"
	@$(PYTHON) tools/gen_next_nex.py --map "$(MAP)" --resident "$(NEXT_RESIDENT)" \
		--ovl "$(BUILD_DIR)/SPECTALK.OVL" --dat "$(BUILD_DIR)/SPECTALK.DAT" \
		--out "$(NEX)" --org $(ZORG)
	@$(PYTHON) tools/test_next_nex_image.py --nex "$(NEX)" --map "$(MAP)" \
		--resident "$(NEXT_RESIDENT)" --ovl "$(BUILD_DIR)/SPECTALK.OVL" \
		--dat "$(BUILD_DIR)/SPECTALK.DAT" --org $(ZORG)

next-info: nex-build
	@bss=$$(grep "__BSS_END_tail" $(MAP) | grep -o "\$$[0-9A-Fa-f]*" | head -1 | tr -d "\$$"); \
	printf "NEX: %s bytes\n" "$$(wc -c < "$(NEX)")"; \
	printf "BSS end: 0x%s; free to ring: %d bytes\n" "$$bss" "$$((0xF500 - 0x$$bss))"; \
	printf "Packed overlay atlas: %s bytes\n" "$$(wc -c < "$(BUILD_DIR)/SPECTALK.OVL")"; \
	printf "DAT: %s bytes\n" "$$(wc -c < "$(BUILD_DIR)/SPECTALK.DAT")"

# ------------------------------------------------------------
# INFO phase (colored, no redundant "(SpecTalkZX.tap)")
# ------------------------------------------------------------
info:
	@for f in "$(TAP)" "$(MAP)" "$(LOG)"; do \
		if [ ! -f "$$f" ]; then \
			printf "$(C_RED)[ERR]$(C_RESET) Missing build artifact: %s (run make first)\n" "$$f"; \
			exit 1; \
		fi; \
	done
	$(call STEP,3/3,Info)
	@printf "$(C_BOLD)Output:$(C_RESET) $(C_YEL)%s$(C_RESET)\n" "$(TAP)"
	@printf "$(C_BOLD)Memory map:$(C_RESET) $(C_YEL)%s$(C_RESET)\n" "$(MAP)"
	@printf "$(C_BOLD)Build log:$(C_RESET) $(C_YEL)%s$(C_RESET)\n" "$(LOG)"
	@printf "$(C_BOLD)UART mode:$(C_RESET) $(C_YEL)%s$(C_RESET)\n" "$(UART_DESC)"
	@if [ "$(BUILD_PROFILE)" != "NORMAL" ]; then printf "$(C_BOLD)Build profile:$(C_RESET) $(C_YEL)$(BUILD_PROFILE)$(C_RESET)\n"; fi
	@printf "$(C_BOLD)Code origin:$(C_RESET) $(C_YEL)%s$(C_RESET)\n" "$(ZORG)"
	@printf "$(C_BOLD)Stack size:$(C_RESET) $(C_YEL)%s bytes$(C_RESET)\n" "$(STACK_SIZE)"
	@printf "$(C_BOLD)Binary TAP size:$(C_RESET) $(C_YEL)%s bytes$(C_RESET)\n" "$$($(SIZE_TAP))"
	$(call HR)

evidence:
	@status=0; \
	$(MAKE) --no-print-directory EVIDENCE=1 all || status=$$?; \
	$(MAKE) --no-print-directory gather_evidence || exit $$?; \
	exit $$status

gather_evidence:
	@rm -rf "$(EVIDENCE_DIR)"
	@mkdir -p "$(EVIDENCE_DIR)"
	@for f in src/*.lis src/*.sym asm/*.lis asm/*.sym overlay/*.lis overlay/*.sym *.lis *.sym "$(BUILD_DIR)"/*.lis "$(BUILD_DIR)"/*.sym; do \
		[ -f "$$f" ] || continue; \
		mv "$$f" "$(EVIDENCE_DIR)/"; \
	done
	@if [ -f "$(BUILD_DIR)/overlay_defs.asm" ]; then mv "$(BUILD_DIR)/overlay_defs.asm" "$(EVIDENCE_DIR)/"; fi
	@if [ -f "$(BUILD_DIR)/bpe_dict.bin" ]; then mv "$(BUILD_DIR)/bpe_dict.bin" "$(EVIDENCE_DIR)/"; fi
	@rm -f "$(BUILD_DIR)"/*.bin 2>/dev/null || true
	@if [ -d "$(BUILD_DIR)/bpe_src" ]; then mv "$(BUILD_DIR)/bpe_src" "$(EVIDENCE_DIR)/"; fi
	@if [ -d "$(BUILD_DIR)/bpe_final" ]; then mv "$(BUILD_DIR)/bpe_final" "$(EVIDENCE_DIR)/"; fi
	@$(PYTHON) tools/test_copt_contract.py --listing-dir "$(EVIDENCE_DIR)"
	$(call OK,Evidence collected in $(EVIDENCE_DIR).)

release:
ifeq ($(PLATFORM),next)
	@$(MAKE) BUILD_PROFILE=RELEASE MAX_ALLOCS_PER_NODE=200000 next-all
else ifeq ($(PLATFORM),spectranext)
	@$(PYTHON) tools/test_spectranext_driver_contract.py "$(SPXN_DIR)"
	@$(MAKE) BUILD_PROFILE=RELEASE MAX_ALLOCS_PER_NODE=200000 all
else
	@$(MAKE) BUILD_PROFILE=RELEASE MAX_ALLOCS_PER_NODE=200000 all
endif
RELEASE:
	@$(MAKE) release
