#!/bin/bash
# =============================================================================
# 脚本名称: crontab.sh
# 用途:   监控 Kokoro TTS 服务端口，如果未运行则自动启动 app.py
# 依赖:   conda(kokoro 环境), lsof, nohup
# 用法:   ./crontab.sh [-p 端口] [-l 日志文件] [-h]
#         crontab 示例: */5 * * * * /path/to/this/dir/crontab.sh >> /path/to/this/dir/crontab.log 2>&1
# =============================================================================

# crontab 环境下 PATH 通常不完整，手动补全
SubPath="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH="$SubPath"
set -uo pipefail
IFS=$'\n\t'

# -------------------- 默认配置 --------------------
readonly DEFAULT_PORT=7860
readonly MAX_CHECKS=3               # 启动失败最大重试次数
readonly CHECK_INTERVAL=5           # 每次重试间隔(秒)
readonly STARTUP_WAIT=3             # 启动后等待端口就绪时间(秒)

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_FILE="${SCRIPT_DIR}/app.py"
readonly CONDA_BASE="/opt/homebrew/Caskroom/miniconda/base"
readonly CONDA_ENV="kokoro"
readonly PYTHON_BIN="${CONDA_BASE}/envs/${CONDA_ENV}/bin/python"

# -------------------- 颜色定义 --------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# -------------------- 参数解析 --------------------
usage() {
    cat <<USAGE
用法: $(basename "$0") [选项]

选项:
    -p PORT    指定服务端口 (默认: ${DEFAULT_PORT})
    -l FILE    指定日志文件 (默认: 脚本目录下 server.log)
    -h         显示本帮助

示例:
    $(basename "$0")                    # 默认端口 7860
    $(basename "$0") -p 8000            # 指定端口 8000
    $(basename "$0") -p 8000 -l a.log   # 指定端口和日志
USAGE
}

PORT="${DEFAULT_PORT}"
LOG_FILE="${SCRIPT_DIR}/server.log"

while getopts "p:l:h" opt; do
    case $opt in
        p) PORT="$OPTARG" ;;
        l) LOG_FILE="$OPTARG" ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

# -------------------- 工具函数 --------------------
log() {
    local level="$1"; shift
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] $*" | tee -a "$LOG_FILE"
}

is_port_running() {
    lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

start_service() {
    log "INFO" "${CYAN}正在后台启动 app.py (端口 ${PORT})...${NC}"

    # 激活 conda 环境后启动（nohup 后台运行，日志追加到 LOG_FILE）
    (
        source "${CONDA_BASE}/etc/profile.d/conda.sh"
        conda activate "${CONDA_ENV}"
        cd "${SCRIPT_DIR}"
        PORT="${PORT}" nohup "${PYTHON_BIN}" "${APP_FILE}" >> "${LOG_FILE}" 2>&1 &
        echo "PID: $!"
    )

    log "INFO" "等待 ${STARTUP_WAIT} 秒让服务就绪..."
    sleep "${STARTUP_WAIT}"
}

# -------------------- 前置检查 --------------------
if [[ ! -f "${APP_FILE}" ]]; then
    log "ERROR" "${RED}✗ 未找到 ${APP_FILE}${NC}"
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    log "ERROR" "${RED}✗ 未找到 Python: ${PYTHON_BIN}${NC}"
    log "ERROR" "${RED}  请确认 conda 环境 ${CONDA_ENV} 已创建${NC}"
    exit 1
fi

# -------------------- 主逻辑 --------------------
main() {
    echo ""
    log "INFO" "${CYAN}========== Kokoro TTS 端口监控启动 ==========${NC}"
    log "INFO" "监控端口: ${PORT}"
    log "INFO" "Python:   ${PYTHON_BIN}"
    log "INFO" "日志文件: ${LOG_FILE}"
    echo ""

    # 端口已在运行，直接退出
    if is_port_running; then
        log "SUCCESS" "${GREEN}✓ 端口 ${PORT} 已在运行中，无需操作${NC}"
        exit 0
    fi

    log "WARN" "${YELLOW}端口 ${PORT} 未运行，开始启动服务...${NC}"

    local check_count=0
    while [ "${check_count}" -lt "${MAX_CHECKS}" ]; do
        check_count=$((check_count + 1))
        log "INFO" "--- 第 ${check_count}/${MAX_CHECKS} 次尝试 ---"

        # 清理可能残留的僵尸进程（占用 app.py 但端口未监听）
        pkill -f "python.*${APP_FILE}" 2>/dev/null || true
        sleep 1

        start_service

        if is_port_running; then
            log "SUCCESS" "${GREEN}✓ 端口 ${PORT} 启动成功!${NC}"
            exit 0
        fi

        log "WARN" "${YELLOW}第 ${check_count} 次启动失败，端口未就绪${NC}"
        if [ "${check_count}" -lt "${MAX_CHECKS}" ]; then
            log "INFO" "等待 ${CHECK_INTERVAL} 秒后重试..."
            sleep "${CHECK_INTERVAL}"
        fi
    done

    log "ERROR" "${RED}✗ 已达最大重试次数 (${MAX_CHECKS})，服务启动失败，请检查 ${LOG_FILE}${NC}"
    exit 1
}

main "$@"
