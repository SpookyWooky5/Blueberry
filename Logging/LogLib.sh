#!/bin/sh
# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 08-MAY-2025  Initial Draft
# 13-JUL-2025  Add manual log rotation for cron jobs.
# ============================================================================ #

# ================================= FUNCTIONS ================================ #

RotateLogFnct() {
    local log_file="$1"
    
    # Check if the log file exists and is a regular file
    if [ -f "$log_file" ]; then
        # Get the modification timestamp of the log file (seconds since epoch)
        local mod_time=$(stat -c %Y "$log_file")
        # Get today's date at midnight (seconds since epoch)
        local today_start=$(date +%s -d "00:00:00")

        # If the log file was last modified before today
        if [ "$mod_time" -lt "$today_start" ]; then
            # Get the modification date of the file for the archive name
            local archive_date=$(date -d "@$mod_time" +%Y-%m-%d)
            local archive_log_file="${log_file}.${archive_date}"

            # Handle cases where the archive file already exists
            if [ -f "$archive_log_file" ]; then
                counter=1
                while [ -f "${archive_log_file}.${counter}" ]; do
                    counter=$((counter + 1))
                done
                archive_log_file="${archive_log_file}.${counter}"
            fi
            
            # Rename the log file
            mv "$log_file" "$archive_log_file" || {
                echo "FATAL: Could not rotate log file: [$log_file]"
                return 1
            }
        fi
    fi
    return 0
}

LogInitFnct() {
	LOG_LIB_LOG_FILE_CREATED="FALSE"
	
	LogLibLogModule="$1"
	LogLibLogFileName="${Log}/${LogLibLogModule}".log

    # Perform rotation before touching the new log file
    RotateLogFnct "$LogLibLogFileName" || exit 9

	touch "${LogLibLogFileName}" || {
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

	if [ "$LOG_LIB_LOG_FILE_CREATED" = "TRUE" ]; then
		printf '%s | %-8s | %-13s | %s-%s | %s() | %s\n' "$(date "+%d-%b-%Y %H:%M:%S")" \
		"$LogLibLogLevel" "$LogLibLogModule" "$(basename "$0")" "${BASH_LINENO[0]}" \
		"${FUNCNAME[1]}" "$LogLibLogMsg" >> "$LogLibLogFileName"
	else
		echo "FATAL: Log File not Initialized!"
		exit 9
	fi
	return 0
}

export -f LogInitFnct
export -f LogFnct
export -f RotateLogFnct
