# !/bin/sh
# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 08-MAY-2025  Initial Draft
# ============================================================================ #

# ============================= GLOBAL VARIABLES ============================= #

# ================================= CONSTANTS ================================ #

# ================================= FUNCTIONS ================================ #

# =================================== MAIN =================================== #

LogInitFnct () {
	LOG_LIB_LOG_FILE_CREATED="FALSE"
	
	LogLibLogModule="$1"
	LogLibLogFileName="${Log}/${LogLibLogModule}".log

	touch ${LogLibLogFileName} || {
		echo "FATAL: Could not write to log file: [${LogLibLogFileName}]"
		exit 9
	}
		
	LOG_LIB_LOG_FILE_CREATED="TRUE"

	export LOG_LIB_LOG_FILE_CREATED
	export LogLibLogModule
	export LogLibLogFileName
	return 0
}

LogFnct() {
	LogLibLogLevel="$1"
	LogLibLogMsg="$2"

	if [ "$LOG_LIB_LOG_FILE_CREATED" = "TRUE" ]
	then
		printf '%s | %-8s | %-13s | %s-%s | %s() | %s\n' "`date "+%d-%b-%Y %H:%M:%S"`" \
		"$LogLibLogLevel" "$LogLibLogModule" "`basename $0`" "${BASH_LINENO[0]}" \
		"${FUNCNAME[1]}" "$LogLibLogMsg" >> "$LogLibLogFileName"
	else
		echo "FATAL: Log File not Initialized!"
		exit 9
	fi
	return 0
}

export -f LogInitFnct
export -f LogFnct